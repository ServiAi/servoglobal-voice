from app.modules.evaluations.application.contracts import EvaluationResultView


class EvaluationQueries:
    def __init__(self, repository: object) -> None:
        self.repository = repository

    def get(self, tenant_id: str, run_id: str) -> EvaluationResultView | None:
        return self.repository.get(tenant_id, run_id)
