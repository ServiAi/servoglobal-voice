from __future__ import annotations

from livekit.agents import AgentServer, JobContext, cli

from .config import load_settings
from .worker import run_job

settings = load_settings()
server = AgentServer(log_level=settings.LOG_LEVEL.lower(), port=settings.HEALTH_PORT)


@server.rtc_session(agent_name=settings.LIVEKIT_AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    await run_job(ctx, settings)


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
