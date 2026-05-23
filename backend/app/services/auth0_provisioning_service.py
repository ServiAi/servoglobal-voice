from __future__ import annotations

from dataclasses import dataclass, replace
import secrets
import string
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import settings


class Auth0ProvisioningError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class Auth0ProvisionedUser:
    user_id: str
    email: str
    name: str | None = None
    connection: str | None = None
    created_via: str = "management_api"
    verification_email_sent: bool = False
    password_reset_triggered: bool = False
    activation_errors: list[str] | None = None


class Auth0ProvisioningService:
    def __init__(
        self,
        *,
        http_client: httpx.Client | None = None,
        settings_obj: Any = settings,
    ) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)
        self._settings = settings_obj
        self._management_token: str | None = None

    def provision_tenant_admin(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        self._validate_configuration()
        provisioned_user = self.create_database_user(email=email, name=name)

        activation_errors: list[str] = []
        verification_email_sent = False
        password_reset_triggered = False

        if self._settings.AUTH0_ONBOARDING_SEND_VERIFICATION_EMAIL:
            if provisioned_user.created_via == "management_api":
                try:
                    self.send_verification_email(provisioned_user.user_id)
                    verification_email_sent = True
                except Auth0ProvisioningError as exc:
                    activation_errors.append(str(exc))
            else:
                try:
                    self.send_verification_email_via_dbconnection(email=email)
                    verification_email_sent = True
                    password_reset_triggered = True
                except Auth0ProvisioningError as exc:
                    activation_errors.append(str(exc))

        if self._settings.AUTH0_ONBOARDING_TRIGGER_PASSWORD_RESET:
            if provisioned_user.created_via == "management_api":
                try:
                    self.trigger_password_reset_email(email=email)
                    password_reset_triggered = True
                except Auth0ProvisioningError as exc:
                    activation_errors.append(str(exc))

        return replace(
            provisioned_user,
            verification_email_sent=verification_email_sent,
            password_reset_triggered=password_reset_triggered,
            activation_errors=activation_errors,
        )

    def create_database_user(self, *, email: str, name: str) -> Auth0ProvisionedUser:
        try:
            return self._create_database_user_with_management_api(email=email, name=name)
        except Auth0ProvisioningError as exc:
            if not self._can_use_authentication_signup_fallback(exc):
                raise
            return self._create_database_user_with_authentication_api(
                email=email,
                name=name,
            )

    def _create_database_user_with_management_api(
        self,
        *,
        email: str,
        name: str,
    ) -> Auth0ProvisionedUser:
        payload = {
            "connection": self._connection_name(),
            "email": email,
            "name": name,
            "password": self._generate_temporary_password(),
            "email_verified": False,
            "verify_email": False,
            "app_metadata": {
                "serviglobal_onboarding": True,
            },
        }
        data = self._management_post("/api/v2/users", payload, expected_status=201)
        user_id = data.get("user_id")
        if not user_id:
            raise Auth0ProvisioningError(
                "Auth0 create user response did not include user_id"
            )
        return Auth0ProvisionedUser(
            user_id=user_id,
            email=data.get("email") or email,
            name=data.get("name") or name,
            connection=self._connection_name(),
            created_via="management_api",
        )

    def _create_database_user_with_authentication_api(
        self,
        *,
        email: str,
        name: str,
    ) -> Auth0ProvisionedUser:
        response = self._post(
            f"{self._auth0_base_url()}/dbconnections/signup",
            operation="call Auth0 Authentication API /dbconnections/signup",
            json={
                "client_id": self._onboarding_app_client_id(),
                "email": email,
                "password": self._generate_temporary_password(),
                "connection": self._connection_name(),
                "name": name,
                "user_metadata": {
                    "serviglobal_onboarding": "true",
                },
            },
        )
        self._ensure_success(
            response,
            operation="call Auth0 Authentication API /dbconnections/signup",
            expected_status=200,
        )
        data = self._response_json(response)
        user_id = self._normalize_database_user_id(data.get("user_id") or data.get("_id"))
        if not user_id:
            raise Auth0ProvisioningError(
                "Auth0 signup response did not include user_id or _id"
            )
        return Auth0ProvisionedUser(
            user_id=user_id,
            email=data.get("email") or email,
            name=data.get("name") or name,
            connection=self._connection_name(),
            created_via="authentication_api_signup",
        )

    def send_verification_email(self, user_id: str) -> None:
        self._management_post(
            "/api/v2/jobs/verification-email",
            {"user_id": user_id},
            expected_status=201,
        )

    def send_verification_email_via_dbconnection(self, *, email: str) -> None:
        """Send email verification via Authentication API (no Management API needed).

        Uses the /dbconnections/change_password endpoint which sends a password
        reset email. This is used as a fallback when Management API is unavailable.
        NOTE: This sends a password reset email, not an email verification email.
        The official email verification uses Management API /api/v2/jobs/verification-email.
        """
        client_id = self._onboarding_app_client_id()
        if not client_id:
            raise Auth0ProvisioningError(
                "AUTH0_ONBOARDING_APP_CLIENT_ID or AUTH0_CLIENT_ID is required "
                "when email verification is enabled"
            )
        response = self._post(
            f"{self._auth0_base_url()}/dbconnections/change_password",
            operation="trigger Auth0 verification email via dbconnection",
            json={
                "client_id": client_id,
                "email": email,
                "connection": self._connection_name(),
            },
        )
        self._ensure_success(
            response,
            operation="trigger Auth0 verification email via dbconnection",
            expected_status=200,
        )

    def trigger_password_reset_email(self, *, email: str) -> None:
        client_id = self._onboarding_app_client_id()
        if not client_id:
            raise Auth0ProvisioningError(
                "AUTH0_ONBOARDING_APP_CLIENT_ID or AUTH0_CLIENT_ID is required "
                "when password reset is enabled"
            )

        response = self._post(
            f"{self._auth0_base_url()}/dbconnections/change_password",
            operation="trigger Auth0 password reset email",
            json={
                "client_id": client_id,
                "email": email,
                "connection": self._connection_name(),
            },
        )
        self._ensure_success(
            response,
            operation="trigger Auth0 password reset email",
            expected_status=200,
        )

    def delete_user(self, user_id: str) -> None:
        encoded_user_id = quote(user_id, safe="")
        response = self._delete(
            f"{self._management_api_base_url()}/users/{encoded_user_id}",
            operation="delete Auth0 user",
            headers=self._authorization_headers(),
        )
        self._ensure_success(
            response,
            operation="delete Auth0 user",
            expected_status=204,
        )

    def _management_post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        expected_status: int,
    ) -> dict[str, Any]:
        response = self._post(
            f"{self._auth0_base_url()}{path}",
            operation=f"call Auth0 Management API {path}",
            json=payload,
            headers=self._authorization_headers(),
        )
        self._ensure_success(
            response,
            operation=f"call Auth0 Management API {path}",
            expected_status=expected_status,
        )
        return self._response_json(response)

    def _authorization_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_management_token()}"}

    def _get_management_token(self) -> str:
        if self._management_token is not None:
            return self._management_token

        response = self._post(
            f"{self._auth0_base_url()}/oauth/token",
            operation="get Auth0 Management API token",
            json={
                "grant_type": "client_credentials",
                "client_id": self._management_client_id(),
                "client_secret": self._management_client_secret(),
                "audience": self._management_audience(),
            },
        )
        self._ensure_success(
            response,
            operation="get Auth0 Management API token",
            expected_status=200,
        )
        token = self._response_json(response).get("access_token")
        if not token:
            raise Auth0ProvisioningError(
                "Auth0 token response did not include access_token"
            )
        self._management_token = token
        return token

    def _post(
        self,
        url: str,
        *,
        operation: str,
        json: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return self._client.post(url, json=json, headers=headers)
        except httpx.HTTPError as exc:
            raise Auth0ProvisioningError(f"Failed to {operation}: {exc}") from exc

    def _delete(
        self,
        url: str,
        *,
        operation: str,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        try:
            return self._client.delete(url, headers=headers)
        except httpx.HTTPError as exc:
            raise Auth0ProvisioningError(f"Failed to {operation}: {exc}") from exc

    def _validate_configuration(self) -> None:
        missing = []
        if not self._management_domain():
            missing.append("AUTH0_MANAGEMENT_DOMAIN or AUTH0_DOMAIN")
        if not self._management_client_id():
            missing.append("AUTH0_MANAGEMENT_CLIENT_ID or AUTH0_CLIENT_ID")
        if not self._management_client_secret():
            missing.append("AUTH0_MANAGEMENT_CLIENT_SECRET or AUTH0_CLIENT_SECRET")
        if not self._connection_name():
            missing.append("AUTH0_ONBOARDING_CONNECTION")
        if (
            self._settings.AUTH0_ONBOARDING_TRIGGER_PASSWORD_RESET
            and not self._onboarding_app_client_id()
        ):
            missing.append("AUTH0_ONBOARDING_APP_CLIENT_ID or AUTH0_CLIENT_ID")
        if missing:
            raise Auth0ProvisioningError(
                "Auth0 onboarding provisioning configuration is incomplete: "
                + ", ".join(missing)
            )

    def _management_api_base_url(self) -> str:
        return f"{self._auth0_base_url()}/api/v2"

    def _auth0_base_url(self) -> str:
        return f"https://{self._management_domain()}"

    def _management_domain(self) -> str:
        domain = (
            self._settings.AUTH0_MANAGEMENT_DOMAIN
            or self._settings.AUTH0_DOMAIN
            or ""
        ).strip()
        return domain.removeprefix("https://").removeprefix("http://").rstrip("/")

    def _management_audience(self) -> str:
        audience = self._settings.AUTH0_MANAGEMENT_AUDIENCE.strip()
        if audience:
            return audience
        return f"{self._auth0_base_url()}/api/v2/"

    def _management_client_id(self) -> str:
        return (
            self._settings.AUTH0_MANAGEMENT_CLIENT_ID
            or self._settings.AUTH0_CLIENT_ID
            or ""
        ).strip()

    def _management_client_secret(self) -> str:
        return (
            self._settings.AUTH0_MANAGEMENT_CLIENT_SECRET
            or self._settings.AUTH0_CLIENT_SECRET
            or ""
        ).strip()

    def _onboarding_app_client_id(self) -> str:
        return (
            self._settings.AUTH0_ONBOARDING_APP_CLIENT_ID
            or self._settings.AUTH0_CLIENT_ID
            or ""
        ).strip()

    def _connection_name(self) -> str:
        connection = self._settings.AUTH0_ONBOARDING_CONNECTION.strip()
        if connection:
            return connection
        return "Username-Password-Authentication"

    def _can_use_authentication_signup_fallback(
        self,
        exc: Auth0ProvisioningError,
    ) -> bool:
        if not self._settings.AUTH0_ONBOARDING_ALLOW_AUTHENTICATION_SIGNUP_FALLBACK:
            return False
        if not self._onboarding_app_client_id():
            return False
        return exc.status_code in {401, 403}

    def _normalize_database_user_id(self, raw_user_id: Any) -> str:
        if not isinstance(raw_user_id, str) or not raw_user_id.strip():
            return ""
        user_id = raw_user_id.strip()
        if "|" in user_id:
            return user_id
        return f"auth0|{user_id}"

    def _ensure_success(
        self,
        response: httpx.Response,
        *,
        operation: str,
        expected_status: int,
    ) -> None:
        if response.status_code == expected_status:
            return
        raise Auth0ProvisioningError(
            f"Failed to {operation}: {response.status_code} {self._response_detail(response)}",
            status_code=response.status_code,
        )

    def _response_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise Auth0ProvisioningError(
                "Auth0 response did not contain valid JSON",
                status_code=response.status_code,
            ) from exc
        if not isinstance(data, dict):
            raise Auth0ProvisioningError(
                "Auth0 response JSON was not an object",
                status_code=response.status_code,
            )
        return data

    def _response_detail(self, response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:500]
        return str(data)[:500]

    def _generate_temporary_password(self) -> str:
        choices = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^&*"),
        ]
        alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
        choices.extend(secrets.choice(alphabet) for _ in range(36))
        secrets.SystemRandom().shuffle(choices)
        return "".join(choices)
