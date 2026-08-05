.PHONY: infra-up infra-down migrate migrate-heads migrate-current backend worker frontend dev lint lint-backend lint-frontend

infra-up:
	docker compose up -d

infra-down:
	docker compose down

migrate:
	unset DATABASE_URL && cd backend && alembic upgrade head

migrate-heads:
	unset DATABASE_URL && cd backend && alembic heads

migrate-current:
	unset DATABASE_URL && cd backend && alembic current

backend:
	unset DATABASE_URL && cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker:
	unset DATABASE_URL && cd backend && python -m app.workers.notification_worker

frontend:
	cd frontend && npm run dev

dev: infra-up
	start cmd /k "set DATABASE_URL=&& cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
	start cmd /k "set DATABASE_URL=&& cd backend && python -m app.workers.notification_worker"
	start cmd /k "cd frontend && npm run dev"

lint-backend:
	cd backend && uvx ruff check app

lint-frontend:
	cd frontend && npm run lint

lint: lint-backend lint-frontend
