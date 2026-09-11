from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    CONTROL_PLANE_BASE_URL: str
    VOICE_RUNTIME_SERVICE_SECRET: str = Field(min_length=32)
    VOICE_RUNTIME_JWT_ISSUER: str = "serviglobal-voice-runtime"
    VOICE_RUNTIME_JWT_AUDIENCE: str = "serviglobal-control-plane"
    LIVEKIT_URL: str
    LIVEKIT_API_KEY: str
    LIVEKIT_API_SECRET: str
    LIVEKIT_AGENT_NAME: str = "serviglobal-voice-runtime"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    HEALTH_PORT: int = 8081
    CONTROL_PLANE_TIMEOUT_SECONDS: float = Field(default=5.0, gt=0, le=30)
    CONTROL_PLANE_MAX_ATTEMPTS: int = Field(default=3, ge=1, le=5)
    VOICE_RUNTIME_PARTICIPANT_WAIT_SECONDS: int = Field(default=60, ge=10, le=300)


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
