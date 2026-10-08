from app.modules.evaluations.public import EvaluationFacade


def evaluations(db: object) -> EvaluationFacade:
    return EvaluationFacade(db)
