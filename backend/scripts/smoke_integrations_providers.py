"""Manual, opt-in provider smoke test for Integrations / Messaging (staging only).

Never runs in CI and never uses credentials from the repository: it reads the target
database (``DATABASE_URL``) and the tenant's own provider configuration, exactly like the
application does. Without ``--execute`` it only resolves configuration (no message leaves).

Safety rails
  * refuses to run unless ``SERVIGLOBAL_STAGING_PROVIDER_SMOKE=1`` is exported;
  * every action needs an explicit test tenant and an explicit test recipient -- nothing is
    sent to a default or arbitrary address;
  * secrets and full phone numbers/emails are never printed (recipients appear masked);
  * outputs are only provider ids and statuses.

Examples (from ``backend/`` against the STAGING database):

    export SERVIGLOBAL_STAGING_PROVIDER_SMOKE=1
    python scripts/smoke_integrations_providers.py whatsapp --tenant-id T --template-key lead_follow_up --to-phone +57300... --execute
    python scripts/smoke_integrations_providers.py resend   --tenant-id T --to-email qa@example.com --execute
    python scripts/smoke_integrations_providers.py chatwoot --tenant-id T --phone +57300... --execute

Exit code: 0 = every step passed, 1 = a step failed, 2 = refused / misconfigured.
Report "not executed: credentials unavailable" when you cannot run it; never fake a result.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

FLAG = "SERVIGLOBAL_STAGING_PROVIDER_SMOKE"
MARK = "[ServiGlobal staging smoke]"


def _mask_phone(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"***{digits[-4:]}" if len(digits) > 4 else "***"


def _mask_email(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}" if domain else "***"


def _step(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}")
    return ok


def smoke_whatsapp(db, args) -> bool:
    from app.modules.integrations.public import WhatsAppFacade

    facade = WhatsAppFacade(db)
    ok = _step("whatsapp config resolves", facade.is_configured(args.tenant_id))
    if not ok:
        return False
    try:
        contract = facade.get_approved_template_contract(args.tenant_id, args.template_key)
    except ValueError as exc:
        return _step("approved template lookup", False, str(exc))
    ok = _step(
        "approved template lookup",
        contract is not None and contract.is_approved,
        f"status={contract.status if contract else 'missing'} variables={list(contract.required_variables) if contract else []}",
    )
    if not ok or not args.execute:
        return ok
    variables = {key: f"{MARK} {key}" for key in contract.required_variables}
    try:
        outcome = facade.send_template(
            tenant_id=args.tenant_id,
            to_phone=args.to_phone,
            template_key=args.template_key,
            variables=variables,
            metadata={"source": "staging_smoke"},
            lead_id=None,
            contact_id=None,
        )
    except ValueError as exc:
        return _step(f"send template to {_mask_phone(args.to_phone)}", False, str(exc))
    return _step(
        f"send template to {_mask_phone(args.to_phone)}",
        outcome.status == "sent" and bool(outcome.provider_message_id),
        f"status={outcome.status} provider_message_id={outcome.provider_message_id}",
    )


def smoke_resend(db, args) -> bool:
    from app.modules.integrations.application.email.config_service import EmailConfigService
    from app.modules.integrations.application.email.send_service import EmailSendService

    config = EmailConfigService(db).get_config(args.tenant_id, "resend")
    ok = _step("resend config resolves", config is not None and config.status == "active", f"status={getattr(config, 'status', None)}")
    if not ok or not args.execute:
        return ok
    try:
        result = EmailSendService(db).send_test_email(tenant_id=args.tenant_id, to_email=args.to_email)
    except ValueError as exc:
        return _step(f"send test email to {_mask_email(args.to_email)}", False, str(exc))
    return _step(
        f"send test email to {_mask_email(args.to_email)}",
        result.status == "sent" and bool(result.provider_email_id),
        f"status={result.status} provider_email_id={result.provider_email_id}",
    )


def smoke_chatwoot(db, args) -> bool:
    from app.modules.integrations.public import ChatwootFacade

    try:
        gateway = ChatwootFacade(db).gateway_for(args.tenant_id)
    except ValueError as exc:
        return _step("chatwoot config resolves", False, str(exc))
    _step("chatwoot config resolves", True)
    if not args.execute:
        return True

    async def run() -> bool:
        contact_id = await gateway.get_or_create_contact(args.phone, MARK, "")
        if not _step(f"find/create test contact {_mask_phone(args.phone)}", bool(contact_id), f"contact_id={contact_id}"):
            return False
        conversation_id = await gateway.get_or_create_conversation(contact_id)
        if not _step("find/create conversation", bool(conversation_id), f"conversation_id={conversation_id}"):
            return False
        noted = await gateway.send_message(conversation_id, f"{MARK} private note", private=True)
        return _step("private note", bool(noted))

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="provider", required=True)
    for name in ("whatsapp", "resend", "chatwoot"):
        item = sub.add_parser(name)
        item.add_argument("--tenant-id", required=True, help="the staging test tenant")
        item.add_argument("--execute", action="store_true", help="actually call the provider (default: config check only)")
    sub.choices["whatsapp"].add_argument("--template-key", required=True)
    sub.choices["whatsapp"].add_argument("--to-phone", required=True, help="explicit test number")
    sub.choices["resend"].add_argument("--to-email", required=True, help="explicit test recipient")
    sub.choices["chatwoot"].add_argument("--phone", required=True, help="explicit test contact phone")
    args = parser.parse_args(argv)

    if os.environ.get(FLAG) != "1":
        print(f"refusing to run: export {FLAG}=1 to confirm this is a STAGING provider smoke test", file=sys.stderr)
        return 2
    if not os.environ.get("DATABASE_URL"):
        print("DATABASE_URL (the staging database) is not set", file=sys.stderr)
        return 2

    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        ok = {"whatsapp": smoke_whatsapp, "resend": smoke_resend, "chatwoot": smoke_chatwoot}[args.provider](db, args)
    finally:
        db.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
