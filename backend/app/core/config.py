from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ULTRAVOX_API_KEY: str
    ULTRAVOX_MODEL: str = "fixie-ai/ultravox-70b"
    ULTRAVOX_WEBHOOK_SECRET: str = ""
    ULTRAVOX_WEBHOOK_SIGNATURE_TOLERANCE_SECONDS: int = 60
    ULTRAVOX_ALLOW_UNSIGNED_WEBHOOKS: bool = False
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
    GOOGLE_CALENDAR_DEFAULT_TIMEZONE: str = "America/Bogota"

    # Turnstile
    TURNSTILE_SECRET_KEY: str | None = None

    # WhatsApp Configuration
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "serviglobal_whatsapp_webhook_token"

    # Chatwoot CRM
    CHATWOOT_API_TOKEN: str = ""
    CHATWOOT_ACCOUNT_ID: int = 1
    CHATWOOT_INBOX_ID: int = 1    # ID del inbox WhatsApp en Chatwoot

    # Tenant integrations
    INTEGRATIONS_ENCRYPTION_KEY: str = ""
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

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
