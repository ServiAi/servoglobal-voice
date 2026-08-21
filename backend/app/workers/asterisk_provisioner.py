from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("asterisk_provisioner")

ROUTE_KEY_RE = re.compile(r"^route-[0-9a-f]{32}$")
ROUTE_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SIP_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
CALLER_ID_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")
PASSWORD_FORBIDDEN = frozenset("\r\n;#[]")


@dataclass(frozen=True)
class ProvisionerSettings:
    api_url: str
    shared_secret: str
    include_path: Path
    state_path: Path
    poll_seconds: float = 15.0
    config_group: str = "asterisk"

    @classmethod
    def from_environment(cls) -> "ProvisionerSettings":
        api_url = os.getenv("SERVIGLOBAL_API_URL", "").rstrip("/")
        shared_secret = os.getenv("ASTERISK_PROVISIONER_SHARED_SECRET", "")
        if not api_url.startswith(("https://", "http://")) or not shared_secret:
            raise ValueError("missing_provisioner_configuration")
        return cls(
            api_url=api_url,
            shared_secret=shared_secret,
            include_path=Path(
                os.getenv(
                    "ASTERISK_TENANTS_INCLUDE_PATH",
                    "/etc/asterisk/pjsip.d/serviglobal-tenants.conf",
                )
            ),
            state_path=Path(
                os.getenv(
                    "ASTERISK_PROVISIONER_STATE_PATH",
                    "/var/lib/serviglobal-asterisk/state.json",
                )
            ),
            poll_seconds=float(os.getenv("ASTERISK_PROVISIONER_POLL_SECONDS", "15")),
            config_group=os.getenv("ASTERISK_CONFIG_GROUP", "asterisk"),
        )


def _validate_route(route: dict[str, Any]) -> None:
    password = route.get("sip_password")
    route_id = str(route.get("route_id", ""))
    route_key = str(route.get("route_key", ""))
    if (
        not ROUTE_ID_RE.fullmatch(route_id)
        or not ROUTE_KEY_RE.fullmatch(route_key)
        or route_key != f"route-{route_id.replace('-', '')}"
    ):
        raise ValueError("invalid_route_key")
    if not SIP_USERNAME_RE.fullmatch(str(route.get("sip_username", ""))):
        raise ValueError("invalid_sip_username")
    if not CALLER_ID_RE.fullmatch(str(route.get("caller_id", ""))):
        raise ValueError("invalid_caller_id")
    if route.get("enabled") and (
        not isinstance(password, str)
        or not password.isascii()
        or not password.isprintable()
        or any(char in PASSWORD_FORBIDDEN for char in password)
    ):
        raise ValueError("invalid_sip_password")


def render_pjsip_include(routes: list[dict[str, Any]]) -> str:
    sections = [
        "; Managed by ServiGlobal Asterisk provisioner. Manual changes are overwritten."
    ]
    usernames: set[str] = set()
    for route in routes:
        _validate_route(route)
        if not route["enabled"]:
            continue
        if route["sip_username"] in usernames:
            raise ValueError("duplicate_sip_username")
        usernames.add(route["sip_username"])
        key = route["route_key"]
        auth_key = f"auth-{key}"
        sections.append(
            "\n".join(
                [
                    f"[{auth_key}]",
                    "type=auth",
                    "auth_type=userpass",
                    f"username={route['sip_username']}",
                    f"password={route['sip_password']}",
                    "",
                    f"[{key}](ultravox-tenant)",
                    f"auth={auth_key}",
                    f"aors={key}",
                    f"callerid={route['caller_id']}",
                    f"set_var=TENANT_ROUTE_ID={route['route_id']}",
                    f"set_var=TENANT_CALLER_ID={route['caller_id']}",
                    "",
                    f"[{key}]",
                    "type=aor",
                    "max_contacts=1",
                    "remove_existing=yes",
                ]
            )
        )
    return "\n\n".join(sections) + "\n"


class AsteriskProvisioner:
    def __init__(self, settings: ProvisionerSettings) -> None:
        self.settings = settings

    def _request(self, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.settings.api_url}/api/v1/internal/asterisk/{path}",
            data=body,
            method="GET" if payload is None else "POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Asterisk-Provisioner-Secret": self.settings.shared_secret,
            },
        )
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read())

    def _last_snapshot(self) -> str | None:
        try:
            return json.loads(self.settings.state_path.read_text("utf-8")).get(
                "snapshot_revision"
            )
        except (FileNotFoundError, OSError, ValueError, AttributeError):
            return None

    def _save_snapshot(self, revision: str) -> None:
        self.settings.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.settings.state_path.with_suffix(".tmp")
        temp.write_text(json.dumps({"snapshot_revision": revision}), encoding="utf-8")
        os.replace(temp, self.settings.state_path)

    def _install(self, content: str) -> Path | None:
        target = self.settings.include_path
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_suffix(target.suffix + ".bak")
        if target.exists():
            shutil.copy2(target, backup)
        else:
            backup = None
        temp = target.with_suffix(target.suffix + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, 0o640)
            try:
                shutil.chown(temp, group=self.settings.config_group)
            except LookupError:
                pass
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return backup

    @staticmethod
    def _asterisk(command: str) -> str:
        result = subprocess.run(
            ["asterisk", "-rx", command],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout

    def _reload_and_verify(self, routes: list[dict[str, Any]]) -> None:
        self._asterisk("pjsip reload")
        for route in routes:
            if route["enabled"]:
                output = self._asterisk(f"pjsip show endpoint {route['route_key']}")
                if route["route_key"] not in output:
                    raise ValueError("endpoint_verification_failed")

    def _restore(self, backup: Path | None) -> None:
        if backup and backup.exists():
            os.replace(backup, self.settings.include_path)
        else:
            self.settings.include_path.unlink(missing_ok=True)
        try:
            self._asterisk("pjsip reload")
        except (OSError, subprocess.SubprocessError):
            logger.error("Asterisk rollback reload failed")

    def reconcile_once(self) -> bool:
        desired = self._request("desired-state")
        revision = desired["snapshot_revision"]
        if revision == self._last_snapshot():
            return False
        routes = desired["routes"]
        backup: Path | None = None
        installed = False
        success = False
        error_code: str | None = None
        try:
            content = render_pjsip_include(routes)
            backup = self._install(content)
            installed = True
            self._reload_and_verify(routes)
            success = True
        except ValueError as exc:
            error_code = str(exc)
            if installed:
                self._restore(backup)
        except subprocess.SubprocessError:
            error_code = "asterisk_reload_failed"
            self._restore(backup)
        except OSError:
            if installed:
                error_code = "asterisk_command_unavailable"
                self._restore(backup)
            else:
                error_code = "config_write_failed"
        report_routes = routes if success else [
            route
            for route in routes
            if route["desired_revision"] != route["applied_revision"]
        ]
        results = [
            {
                "route_id": route["route_id"],
                "revision": route["desired_revision"],
                "success": success,
                "error_code": error_code,
            }
            for route in report_routes
        ]
        if results:
            self._request("apply-results", {"results": results})
        if success:
            self._save_snapshot(revision)
        return success

    def run_forever(self) -> None:
        while True:
            try:
                self.reconcile_once()
            except (HTTPError, URLError, TimeoutError, ValueError, KeyError, OSError) as exc:
                logger.error(
                    "Asterisk provisioning cycle failed",
                    extra={"error_type": type(exc).__name__},
                )
            time.sleep(self.settings.poll_seconds)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    AsteriskProvisioner(ProvisionerSettings.from_environment()).run_forever()


if __name__ == "__main__":
    main()
