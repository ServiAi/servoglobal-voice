from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ULTRAVOX_API_KEY: str
    ULTRAVOX_MODEL: str = "fixie-ai/ultravox-70b"
    ULTRAVOX_WEBHOOK_SECRET: str = ""
    PORT: int = 8000
    DEFAULT_AGENT_ID: str | None = None
    DATABASE_URL: str = "postgresql+psycopg://serviai:serviai@localhost:5432/serviai"

    # Auth0
    AUTH0_DOMAIN: str = ""
    AUTH0_AUDIENCE: str = ""
    AUTH0_ISSUER: str = ""
    AUTH0_ALGORITHMS: str = "RS256"
    AUTH0_AUTO_CREATE_USERS: bool = True

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
    CAL_API_KEY: str = ""
    CAL_EVENT_TYPE_ID: str = ""
    CAL_USERNAME: str = ""
    CAL_TIMEZONE: str = "America/Bogota"

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

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()
