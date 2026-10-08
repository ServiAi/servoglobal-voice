class EvaluationError(Exception):
    code = "evaluation_error"


class EvaluationInvalidEvidence(EvaluationError):
    code = "evaluation_invalid_evidence"


class EvaluationInvalidDefinition(EvaluationError):
    code = "evaluation_invalid_definition"


class EvaluationDefinitionVersionImmutable(EvaluationError):
    code = "evaluation_definition_version_immutable"


class EvaluationDefinitionNotFound(EvaluationError):
    code = "evaluation_definition_not_found"


class EvaluationSubjectNotFound(EvaluationError):
    code = "evaluation_subject_not_found"


class EvaluationSubjectTenantMismatch(EvaluationError):
    code = "evaluation_subject_tenant_mismatch"


class EvaluationEvidenceConflict(EvaluationError):
    code = "evaluation_evidence_conflict"


class EvaluationClaimLost(EvaluationError):
    code = "evaluation_claim_lost"


class SemanticEvaluationError(EvaluationError):
    """Typed semantic failure. ``retryable`` is read by the worker; ``code`` is a safe,
    stable string (never provider text, prompts or evidence)."""

    code = "semantic_evaluation_error"
    retryable = False

    def __init__(self, code: str | None = None) -> None:
        if code is not None:
            self.code = code
        super().__init__(self.code)


class SemanticEvidenceMissing(SemanticEvaluationError):
    code = "semantic_evidence_missing"


class SemanticPromptNotFound(SemanticEvaluationError):
    code = "semantic_prompt_not_found"


class SemanticRubricInvalid(SemanticEvaluationError):
    code = "semantic_rubric_invalid"


class SemanticInputLimitExceeded(SemanticEvaluationError):
    code = "semantic_input_limit_exceeded"


class SemanticJudgeConfigurationError(SemanticEvaluationError):
    code = "semantic_judge_configuration_error"


class SemanticJudgeTimeout(SemanticEvaluationError):
    code = "semantic_judge_timeout"
    retryable = True


class SemanticJudgeRateLimited(SemanticEvaluationError):
    code = "semantic_judge_rate_limited"
    retryable = True


class SemanticJudgeUnavailable(SemanticEvaluationError):
    code = "semantic_judge_unavailable"
    retryable = True


class SemanticJudgeInvalidOutput(SemanticEvaluationError):
    code = "semantic_judge_invalid_output"
    retryable = True


class SemanticJudgeEvidenceMismatch(SemanticEvaluationError):
    """The judge cited evidence that does not exist: fail closed, never store it."""

    code = "semantic_judge_evidence_mismatch"
    retryable = True
