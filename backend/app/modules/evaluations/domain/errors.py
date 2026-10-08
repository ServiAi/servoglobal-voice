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
