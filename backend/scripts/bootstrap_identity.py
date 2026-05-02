from __future__ import annotations

from app.db.session import SessionLocal
from app.services.bootstrap_service import BootstrapConfigurationError, IdentityBootstrapService


def main() -> None:
    with SessionLocal() as db:
        try:
            result = IdentityBootstrapService(db).run_initial_bootstrap()
        except BootstrapConfigurationError as exc:
            raise SystemExit(str(exc)) from exc

    print(
        "Bootstrap complete: "
        f"tenant={result.tenant_id} "
        f"user={result.user_id} "
        f"membership={result.membership_id} "
        f"created_tenant={result.created_tenant} "
        f"created_user={result.created_user} "
        f"created_membership={result.created_membership}"
    )


if __name__ == "__main__":
    main()
