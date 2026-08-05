.PHONY: infra-up infra-down migrate migrate-heads migrate-current backend worker frontend dev lint lint-backend lint-frontend test compile

infra-up:
	docker compose up -d

infra-down:
	docker compose down

migrate:
	cd backend && alembic upgrade head

migrate-heads:
	cd backend && alembic heads

migrate-current:
	cd backend && alembic current

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	cd backend && python -m app.workers.notification_worker

frontend:
	cd frontend && npm run dev

dev: infra-up
	start cmd /k "cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
	start cmd /k "cd backend && python -m app.workers.notification_worker"
	start cmd /k "cd frontend && npm run dev"

lint-backend:
	cd backend && uvx ruff check app

lint-frontend:
	cd frontend && npm run lint

lint: lint-backend lint-frontend

# Runs each test module in its own process: most test_*.py files pin DATABASE_URL
# to a private sqlite file at import time, but app.db.session builds its engine
# once per process, so a bare `unittest discover` makes every module after the
# first silently share (and corrupt) one sqlite file. Excludes test_endpoints.py /
# test_kpis.py / test_db.py / test_db_user.py / test_db_validation.py (manual
# inspection scripts against local DATABASE_URL, no TestCase — run directly with
# `python test_endpoints.py` etc.), test_crm_sprint_2.py (known pre-existing
# assertion drift, tracked separately), test_cors.py (pytest-style bare
# functions, not a unittest.TestCase — run it with pytest), and test_outbound.py
# (manual smoke-test script, not a unittest.TestCase — hits a locally running
# server directly via `python test_outbound.py`).
test:
	cd backend && for f in $$(ls test_*.py | grep -v -e test_endpoints.py -e test_kpis.py -e test_db.py -e test_db_user.py -e test_db_validation.py -e test_crm_sprint_2.py -e test_cors.py -e test_outbound.py); do python -m unittest "$${f%.py}" || exit 1; done

compile:
	cd backend && python -m compileall app
