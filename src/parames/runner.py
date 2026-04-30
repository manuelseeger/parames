from __future__ import annotations

import logging
from pathlib import Path

from parames.config import AppConfig, RuntimeSettings, definition_to_profile, load_app_config, resolve_profile_defaults
from parames.delivery.delivery_cli import ConsoleChannel, DeliveryChannel
from parames.delivery.delivery_telegram import TelegramChannel
from parames.domain import CandidateWindow
from parames.evaluation import evaluate
from parames.forecast import OpenMeteoForecastClient
from parames.persistence import AlertRepository, build_engine

logger = logging.getLogger(__name__)


def default_config_path() -> Path:
    return RuntimeSettings().config_path


def build_channels(app_config: AppConfig, settings: RuntimeSettings) -> dict[str, DeliveryChannel]:
    if settings.dev_mode:
        redirected = [n for n, c in app_config.delivery_channels.items() if c.type != "console"]
        if redirected:
            logger.warning("DEV MODE: redirecting to console: %s", ", ".join(redirected))

    channels: dict[str, DeliveryChannel] = {}
    for name, cfg in app_config.delivery_channels.items():
        if cfg.type == "console" or settings.dev_mode:
            channels[name] = ConsoleChannel()
        elif cfg.type == "telegram":
            if settings.telegram_bot_token is None:
                raise ValueError(
                    f"delivery_channels.{name}: PARAMES_TELEGRAM_BOT_TOKEN is not set"
                )
            chat_id = (cfg.model_extra or {}).get("chat_id")
            if not chat_id:
                raise ValueError(f"delivery_channels.{name}: 'chat_id' is required")
            channels[name] = TelegramChannel(
                bot_token=settings.telegram_bot_token.get_secret_value(),
                chat_id=chat_id,
            )
        else:
            raise ValueError(f"Unsupported delivery channel type: {cfg.type!r}")
    return channels


def _resolve_suppress(
    alert_suppress: bool | None,
    channel_suppress: bool | None,
    channel_type: str,
) -> bool:
    if alert_suppress is not None:
        return alert_suppress
    if channel_suppress is not None:
        return channel_suppress
    return channel_type != "console"


async def _deliver_window(
    *,
    profile_name: str,
    window: CandidateWindow,
    detection_doc,
    channel_names: list[str],
    channels: dict[str, DeliveryChannel],
    channel_types: dict[str, str],
    channel_suppress: dict[str, bool],
    repo: AlertRepository,
    run_id,
) -> tuple[int, int]:
    """Returns (attempted, suppressed) counts for one window."""
    attempted = 0
    suppressed = 0
    for channel_name in channel_names:
        channel = channels.get(channel_name)
        if channel is None:
            raise ValueError(f"Unsupported delivery channel: {channel_name!r}")
        if not channel_suppress[channel_name]:
            await channel.deliver(profile_name, [window])
            continue
        if await repo.was_delivered(detection_doc.id, channel_name):
            suppressed += 1
            continue
        attempted += 1
        try:
            await channel.deliver(profile_name, [window])
        except Exception as exc:  # noqa: BLE001
            await repo.record_delivery(
                detection_id=detection_doc.id,
                run_id=run_id,
                channel_name=channel_name,
                channel_type=channel_types[channel_name],
                status="failed",
                error=str(exc),
            )
            continue
        await repo.record_delivery(
            detection_id=detection_doc.id,
            run_id=run_id,
            channel_name=channel_name,
            channel_type=channel_types[channel_name],
            status="sent",
        )
    return attempted, suppressed


async def run(config_path: Path) -> None:
    settings = RuntimeSettings()
    app_config = load_app_config(config_path)
    channels = build_channels(app_config, settings)
    channel_types = {name: cfg.type for name, cfg in app_config.delivery_channels.items()}

    engine = build_engine(settings.mongo_uri)
    repo = AlertRepository(engine)

    definitions = await repo.list_alert_definitions(enabled_only=True)
    if not definitions:
        logger.warning("No alert definitions in DB. Run 'parames seed' to populate from YAML.")
        return

    resolved = [
        resolve_profile_defaults(definition_to_profile(d), app_config.defaults)
        for d in definitions
    ]

    run_doc = await repo.start_run(
        config_path=str(config_path),
        alert_definition_ids=[d.id for d in definitions],
    )

    windows_found = 0
    deliveries_attempted = 0
    deliveries_suppressed = 0
    status: str = "completed"
    error: str | None = None
    try:
        with OpenMeteoForecastClient() as client:
            for definition, profile in zip(definitions, resolved):
                profile_suppress = {
                    ch: _resolve_suppress(
                        profile.suppress_duplicates,
                        app_config.delivery_channels[ch].suppress_duplicates,
                        app_config.delivery_channels[ch].type,
                    )
                    for ch in profile.delivery
                }
                profile_windows = evaluate(profile, client=client)
                windows_found += len(profile_windows)
                for window in profile_windows:
                    existing = await repo.find_matching_detection(profile.name, window)
                    detection_doc = await repo.upsert_detection(
                        window,
                        alert_definition_id=definition.id,
                        run_id=run_doc.id,
                        existing=existing,
                    )
                    attempted, suppressed = await _deliver_window(
                        profile_name=profile.name,
                        window=window,
                        detection_doc=detection_doc,
                        channel_names=profile.delivery,
                        channels=channels,
                        channel_types=channel_types,
                        channel_suppress=profile_suppress,
                        repo=repo,
                        run_id=run_doc.id,
                    )
                    deliveries_attempted += attempted
                    deliveries_suppressed += suppressed
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        error = str(exc)
        raise
    finally:
        await repo.finish_run(
            run_doc,
            status=status,  # type: ignore[arg-type]
            error=error,
            windows_found=windows_found,
            deliveries_attempted=deliveries_attempted,
            deliveries_suppressed=deliveries_suppressed,
        )
