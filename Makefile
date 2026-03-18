.PHONY: backend frontend dev

backend:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

frontend:
	cd frontend && npm run dev

dev:
	start cmd /k "cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
	start cmd /k "cd frontend && npm run dev"
