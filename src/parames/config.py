from __future__ import annotations

import logging
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pyodmongo import MainBaseModel
from aiogram.utils.token import validate_token as validate_telegram_token

from parames.common import LocationConfig
from parames.plugins.schemas import PluginConfig

logger = logging.getLogger(__name__)


__all__ = [
    "AlertProfileConfig",
    "AppConfig",
    "DefaultsConfig",
    "DeliveryChannelConfig",
    "DryConfig",
    "LocationConfig",
    "ModelAgreementConfig",
    "RuntimeSettings",
    "SchedulerConfig",
    "TimeWindowConfig",
    "WindConfig",
    "definition_to_profile",
    "load_app_config",
    "resolve_profile_defaults",
]


class ModelAgreementConfig(MainBaseModel):
    required: bool = True
    min_models_matching: int = Field(default=2, ge=1)
    max_direction_delta_deg: float = Field(default=35.0, ge=0, le=180)
    max_speed_delta_kmh: float = Field(default=8.0, ge=0)


class DefaultsConfig(BaseModel):
    forecast_hours: int = Field(default=48, ge=1, le=72)
    wind_level_m: int = Field(default=10, ge=1)
    model_agreement: ModelAgreementConfig = Field(default_factory=ModelAgreementConfig)


class WindConfig(MainBaseModel):
    min_speed_kmh: float = Field(ge=0)
    strong_speed_kmh: float = Field(ge=0)
    direction_min_deg: float = Field(ge=0, lt=360)
    direction_max_deg: float = Field(ge=0, lt=360)
    min_consecutive_hours: int = Field(default=2, ge=1)


class TimeWindowConfig(MainBaseModel):
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def validate_window(self) -> "TimeWindowConfig":
        if self.start_hour >= self.end_hour:
            raise ValueError("time_window.start_hour must be lower than end_hour")
        return self


class DryConfig(MainBaseModel):
    enabled: bool = False
    max_precipitation_mm_per_hour: float = Field(default=0.2, ge=0)


class DeliveryChannelConfig(BaseModel):
    type: str
    suppress_duplicates: bool | None = None
    model_config = ConfigDict(extra="allow")


class SchedulerConfig(BaseModel):
    cron_hour: str = "*/6"
    cron_minute: str | None = None


class AlertProfileConfig(BaseModel):
    name: str
    description: str | None = None
    location: LocationConfig
    models: list[str] = Field(min_length=1)
    forecast_hours: int = Field(default=48, ge=1, le=72)
    wind_level_m: int | None = Field(default=None, ge=1)
    model_agreement: ModelAgreementConfig | None = None
    wind: WindConfig
    time_window: TimeWindowConfig | None = None
    dry: DryConfig | None = None
    plugins: list[PluginConfig] = Field(default_factory=list)
    delivery: list[str] = Field(min_length=1)
    suppress_duplicates: bool | None = None

    @model_validator(mode="after")
    def validate_model_count(self) -> "AlertProfileConfig":
        agreement = self.model_agreement
        if agreement is not None and agreement.min_models_matching > len(self.models):
            raise ValueError("model_agreement.min_models_matching cannot exceed model count")
        return self


class AppConfig(BaseModel):
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)

    alerts: list[AlertProfileConfig] = Field(default_factory=list)
    delivery_channels: dict[str, DeliveryChannelConfig]

    @model_validator(mode="after")
    def apply_defaults(self) -> "AppConfig":
        self.alerts = [resolve_profile_defaults(alert, self.defaults) for alert in self.alerts]
        return self

    @model_validator(mode="after")
    def validate_config(self) -> "AppConfig":
        for name, channel in self.delivery_channels.items():
            if channel.type == "telegram":
                settings = RuntimeSettings()
                if not validate_telegram_token(settings.telegram_bot_token.get_secret_value() if settings.telegram_bot_token else ""):
                    logger.error(f"Telegram bot token not set for channel '{name}'. Set PARAMES_TELEGRAM_BOT_TOKEN env var.")
                break

        return self


class RuntimeSettings(BaseSettings):
    config_path: Path = Path("config/default.yaml")
    telegram_bot_token: SecretStr | None = None
    mongo_uri: str = "mongodb://localhost:27017/parames"
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)

    model_config = SettingsConfigDict(
        env_prefix="PARAMES_",
        env_file=".env",
        extra="ignore",
        env_nested_delimiter="__",
    )


def definition_to_profile(definition: object) -> "AlertProfileConfig":
    """Convert an AlertDefinition (or any dict-like) to AlertProfileConfig for evaluation."""
    from pyodmongo import DbModel

    if isinstance(definition, DbModel):
        data = definition.model_dump()
    elif isinstance(definition, dict):
        data = definition
    else:
        data = definition.__dict__
    return AlertProfileConfig.model_validate(data)


def resolve_profile_defaults(
    profile: AlertProfileConfig, defaults: DefaultsConfig
) -> AlertProfileConfig:
    return profile.model_copy(
        update={
            "forecast_hours": profile.forecast_hours or defaults.forecast_hours,
            "wind_level_m": profile.wind_level_m or defaults.wind_level_m,
            "model_agreement": profile.model_agreement or defaults.model_agreement,
        }
    )


def load_app_config(path: Path) -> AppConfig:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Config file not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config file: {path}") from exc

    try:
        return AppConfig.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid app config: {exc}") from exc
