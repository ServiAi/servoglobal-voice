"""Stable CLI entry point for the Notifications worker."""

from app.modules.notifications.public import run_worker_cli

if __name__ == "__main__":
    raise SystemExit(run_worker_cli())
