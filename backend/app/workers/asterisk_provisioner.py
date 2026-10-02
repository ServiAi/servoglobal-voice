"""Entrypoint of the PBX-side Asterisk provisioning agent.

Deployed as ``python -m app.workers.asterisk_provisioner`` (see
ops/asterisk/serviglobal-asterisk-provisioner.service and docs/OPERATIONS.md),
so this launcher keeps that command stable. The agent itself belongs to
Telephony: app/modules/telephony/infrastructure/asterisk_agent.py. It is
imported directly (not through telephony.public) on purpose: the agent runs on
the PBX with only the standard library and must not pull in the rest of the
backend's dependencies.
"""

from app.modules.telephony.infrastructure.asterisk_agent import main

if __name__ == "__main__":
    main()
