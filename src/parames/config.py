from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LocationConfig(BaseModel):
    name: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ModelAgreementConfig(BaseModel):
    required: bool = True
    min_models_matching: int = Field(default=2, ge=1)
    max_direction_delta_deg: float = Field(default=35.0, ge=0, le=180)
    max_speed_delta_kmh: float = Field(default=8.0, ge=0)


class DefaultsConfig(BaseModel):
    forecast_hours: int = Field(default=48, ge=1, le=72)
    wind_level_m: int = Field(default=10, ge=1)
    model_agreement: ModelAgreementConfig = Field(default_factory=ModelAgreementConfig)


class WindConfig(BaseModel):
    min_speed_kmh: float = Field(ge=0)
    strong_speed_kmh: float = Field(ge=0)
    direction_min_deg: float = Field(ge=0, lt=360)
    direction_max_deg: float = Field(ge=0, lt=360)
    min_consecutive_hours: int = Field(default=2, ge=1)


class TimeWindowConfig(BaseModel):
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def validate_window(self) -> "TimeWindowConfig":
        if self.start_hour >= self.end_hour:
            raise ValueError("time_window.start_hour must be lower than end_hour")
        return self


class DryConfig(BaseModel):
    enabled: bool = False
    max_precipitation_mm_per_hour: float = Field(default=0.2, ge=0)


class BiseConfig(BaseModel):
    enabled: bool = True
    east_minus_west_pressure_hpa_min: float = Field(default=1.5, ge=0)
    boost_if_bise: bool = True
    pressure_reference_west: LocationConfig
    pressure_reference_east: LocationConfig


class DeliveryChannelConfig(BaseModel):
    type: str
    model_config = ConfigDict(extra="allow")


class SchedulerConfig(BaseModel):
    cron_hour: str = "*/6"

class AlertProfileConfig(BaseModel):
    name: str
    description: str | None = None
    location: LocationConfig
    models: list[str] = Field(min_length=1)
    forecast_hours: int | None = Field(default=None, ge=1, le=72)
    wind_level_m: int | None = Field(default=None, ge=1)
    model_agreement: ModelAgreementConfig | None = None
    wind: WindConfig
    time_window: TimeWindowConfig | None = None
    dry: DryConfig | None = None
    bise: BiseConfig | None = None
    delivery: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_model_count(self) -> "AlertProfileConfig":
        agreement = self.model_agreement
        if agreement is not None and agreement.min_models_matching > len(self.models):
            raise ValueError("model_agreement.min_models_matching cannot exceed model count")
        return self


class AppConfig(BaseModel):
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    alerts: list[AlertProfileConfig]
    delivery_channels: dict[str, DeliveryChannelConfig]

    @model_validator(mode="after")
    def apply_defaults(self) -> "AppConfig":
        resolved_alerts: list[AlertProfileConfig] = []
        for alert in self.alerts:
            resolved = alert.model_copy(
                update={
                    "forecast_hours": alert.forecast_hours or self.defaults.forecast_hours,
                    "wind_level_m": alert.wind_level_m or self.defaults.wind_level_m,
                    "model_agreement": alert.model_agreement or self.defaults.model_agreement,
                }
            )
            resolved_alerts.append(resolved)
        self.alerts = resolved_alerts
        return self


class RuntimeSettings(BaseSettings):
    config_path: Path = Path("config/default.yaml")
    telegram_bot_token: SecretStr | None = None
    mongo_uri: str = "mongodb://localhost:27017/parames"

    model_config = SettingsConfigDict(
        env_prefix="PARAMES_",
        env_file=".env",
        extra="ignore",
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
