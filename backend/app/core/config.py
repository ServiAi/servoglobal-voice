from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ULTRAVOX_API_KEY: str
    ULTRAVOX_MODEL: str = "fixie-ai/ultravox-70b"
    ULTRAVOX_WEBHOOK_SECRET: str = ""
    ULTRAVOX_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS: int = 60
    ULTRAVOX_ALLOW_UNSIGNED_WEBHOOKS: bool = False
    VOICE_TOOL_SHARED_SECRET: str = ""
    PORT: int = 8000
    DEFAULT_AGENT_ID: str | None = None
    DATABASE_URL: str = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai"
    CORS_ORIGINS: str = (
        "https://www.serviglobal-ia.com,"
        "https://serviglobal-ia.com,"
        "https://staging.serviglobal-ia.com,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000"
    )
    CORS_ORIGIN_REGEX: str = r"https://([a-zA-Z0-9-]+\.)*serviglobal-ia\.com"

    # Auth0
    AUTH0_DOMAIN: str = ""
    AUTH0_CLIENT_ID: str = ""
    AUTH0_CLIENT_SECRET: str = ""
    AUTH0_AUDIENCE: str = ""
    AUTH0_ISSUER: str = ""
    AUTH0_ALGORITHMS: str = "RS256"
    AUTH0_AUTO_CREATE_USERS: bool = True
    AUTH0_MANAGEMENT_DOMAIN: str = ""
    AUTH0_MANAGEMENT_CLIENT_ID: str = ""
    AUTH0_MANAGEMENT_CLIENT_SECRET: str = ""
    AUTH0_MANAGEMENT_AUDIENCE: str = ""
    AUTH0_ONBOARDING_CONNECTION: str = ""
    AUTH0_ONBOARDING_APP_CLIENT_ID: str = ""
    AUTH0_ONBOARDING_SEND_VERIFICATION_EMAIL: bool = True
    AUTH0_ONBOARDING_TRIGGER_PASSWORD_RESET: bool = True
    AUTH0_ONBOARDING_ALLOW_AUTHENTICATION_SIGNUP_FALLBACK: bool = True

    # Initial private app bootstrap
    BOOTSTRAP_TENANT_NAME: str = "ServiGlobal IA"
    BOOTSTRAP_TENANT_SLUG: str = "serviglobal-ia"
    BOOTSTRAP_TENANT_TIMEZONE: str = "America/Bogota"
    BOOTSTRAP_USER_AUTH0_SUB: str = ""
    BOOTSTRAP_USER_EMAIL: str = ""
    BOOTSTRAP_USER_NAME: str = ""
    BOOTSTRAP_USER_ROLE: str = "tenant_admin"

    # SIP / Asterisk Configuration
    ASTERISK_PUBLIC_HOST: str = "54.243.24.145"
    UVX_SIP_USERNAME: str | None = None
    UVX_SIP_PASSWORD: str | None = None

    # Cal.com Configuration
    CALCOM_API_BASE_URL: str = "https://api.cal.com/v2"
    CALCOM_API_VERSION: str = "2024-08-13"
    LEGACY_CALCOM_TENANT_SLUG: str = "serviglobal-ia"
    CAL_API_KEY: str = ""
    CAL_EVENT_TYPE_ID: str = ""
    CAL_USERNAME: str = ""
    CAL_TIMEZONE: str = "America/Bogota"
    CALCOM_WEBHOOK_SECRET: str = ""

    # Google Calendar foundation
    GOOGLE_CALENDAR_OAUTH_CLIENT_ID: str = ""
    GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET: str = ""
    GOOGLE_CALENDAR_REDIRECT_URI: str = ""
    GOOGLE_CALENDAR_FRONTEND_REDIRECT_URL: str = ""
    GOOGLE_CALENDAR_DEFAULT_TIMEZONE: str = "America/Bogota"

    # Turnstile
    TURNSTILE_SECRET_KEY: str | None = None
    VOICE_CONTEXT_SESSION_TTL_SECONDS: int = 600
    VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_GLOBAL_IP_PER_MINUTE: int = 20
    VOICE_PUBLIC_SUBMISSION_RATE_LIMIT_TENANT_IP_PER_MINUTE: int = 5
    VOICE_PUBLIC_CALL_LAUNCH_RATE_LIMIT_GLOBAL_IP_PER_MINUTE: int = 20
    VOICE_PUBLIC_CALL_LAUNCH_RATE_LIMIT_TENANT_IP_PER_MINUTE: int = 5
    VOICE_RUNTIME_RESERVED_LEASE_SECONDS: int = 30
    VOICE_RUNTIME_STARTING_LEASE_SECONDS: int = 60
    VOICE_RUNTIME_PROVIDER_TIMEOUT_SECONDS: float = 15.0
    VOICE_CALLBACK_STARTING_LEASE_SECONDS: int = 120
    VOICE_CALLBACK_RECONCILE_AFTER_SECONDS: int = 30
    VOICE_CALLBACK_MAX_ACTIVE_SECONDS: int = 7200
    VOICE_PUBLIC_RATE_LIMIT_HASH_SECRET: str = ""
    TRUST_CLOUDFLARE_CONNECTING_IP: bool = False

    # WhatsApp Configuration
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "serviglobal_whatsapp_webhook_token"
    WHATSAPP_GRAPH_VERSION: str = "v25.0"
    META_APP_SECRET: str = ""

    # Tenant integrations
    INTEGRATIONS_ENCRYPTION_KEY: str = ""
    ASTERISK_PROVISIONER_SHARED_SECRET: str = ""
    EMAIL_ASSETS_STORAGE_DRIVER: str = "local"
    EMAIL_ASSETS_STORAGE_PATH: str = "storage/email-assets"
    EMAIL_ASSETS_BUCKET: str = ""
    EMAIL_ASSETS_S3_ENDPOINT: str = ""
    EMAIL_ASSETS_S3_REGION: str = "us-east-1"
    EMAIL_ASSETS_S3_ACCESS_KEY: str = ""
    EMAIL_ASSETS_S3_SECRET_KEY: str = ""
    EMAIL_ASSETS_S3_FORCE_PATH_STYLE: bool = True
    EMAIL_MAX_ATTACHMENT_BYTES: int = 10485760
    EMAIL_MAX_TOTAL_ATTACHMENTS_BYTES: int = 15728640
    PUBLIC_FORM_BASE_URL: str = "https://staging.serviglobal-ia.com"
    BACKEND_PUBLIC_BASE_URL: str = ""

    # Chatwoot Platform API (auto-provisioning de Accounts en modo "managed")
    CHATWOOT_PLATFORM_API_TOKEN: str = ""

    # Durable notification worker (Phase 6)
    NOTIFICATION_WORKER_BATCH_SIZE: int = 25
    NOTIFICATION_WORKER_POLL_SECONDS: float = 5.0
    NOTIFICATION_WORKER_LEASE_SECONDS: int = 120
    NOTIFICATION_WORKER_MAX_ATTEMPTS: int = 5
    NOTIFICATION_WORKER_BASE_RETRY_SECONDS: int = 30
    NOTIFICATION_WORKER_MAX_RETRY_SECONDS: int = 3600
    NOTIFICATION_WORKER_JITTER_SECONDS: int = 10
    NOTIFICATION_WORKER_RECOVERY_BATCH_SIZE: int = 50
    NOTIFICATION_WORKER_RECOVERY_INTERVAL_SECONDS: int = 60
    NOTIFICATION_WORKER_LEGACY_STALE_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()


class NotificationWorkerConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class NotificationWorkerSettings:
    """Validated, immutable snapshot of the durable notification worker configuration."""

    batch_size: int
    poll_seconds: float
    lease_seconds: int
    max_attempts: int
    base_retry_seconds: int
    max_retry_seconds: int
    jitter_seconds: int
    recovery_batch_size: int
    recovery_interval_seconds: int
    legacy_stale_seconds: int

    @classmethod
    def from_settings(cls, source: "Settings") -> "NotificationWorkerSettings":
        config = cls(
            batch_size=source.NOTIFICATION_WORKER_BATCH_SIZE,
            poll_seconds=source.NOTIFICATION_WORKER_POLL_SECONDS,
            lease_seconds=source.NOTIFICATION_WORKER_LEASE_SECONDS,
            max_attempts=source.NOTIFICATION_WORKER_MAX_ATTEMPTS,
            base_retry_seconds=source.NOTIFICATION_WORKER_BASE_RETRY_SECONDS,
            max_retry_seconds=source.NOTIFICATION_WORKER_MAX_RETRY_SECONDS,
            jitter_seconds=source.NOTIFICATION_WORKER_JITTER_SECONDS,
            recovery_batch_size=source.NOTIFICATION_WORKER_RECOVERY_BATCH_SIZE,
            recovery_interval_seconds=source.NOTIFICATION_WORKER_RECOVERY_INTERVAL_SECONDS,
            legacy_stale_seconds=source.NOTIFICATION_WORKER_LEGACY_STALE_SECONDS,
        )
        config._validate()
        return config

    def _validate(self) -> None:
        invalid: list[str] = []
        if not (1 <= self.batch_size <= 100):
            invalid.append("batch_size")
        if not (1 <= self.poll_seconds <= 60):
            invalid.append("poll_seconds")
        if not (30 <= self.lease_seconds <= 900):
            invalid.append("lease_seconds")
        if not (1 <= self.max_attempts <= 10):
            invalid.append("max_attempts")
        if not (5 <= self.base_retry_seconds <= 3600):
            invalid.append("base_retry_seconds")
        if self.max_retry_seconds < self.base_retry_seconds:
            invalid.append("max_retry_seconds")
        if not (0 <= self.jitter_seconds <= 300):
            invalid.append("jitter_seconds")
        if not (1 <= self.recovery_batch_size <= 200):
            invalid.append("recovery_batch_size")
        if not (10 <= self.recovery_interval_seconds <= 3600):
            invalid.append("recovery_interval_seconds")
        if not (60 <= self.legacy_stale_seconds <= 3600):
            invalid.append("legacy_stale_seconds")
        if invalid:
            raise NotificationWorkerConfigurationError(
                f"invalid_notification_worker_settings:{','.join(invalid)}"
            )
