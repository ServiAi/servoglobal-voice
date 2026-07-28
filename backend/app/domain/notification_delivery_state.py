from __future__ import annotations

PENDING = "pending"
PROCESSING = "processing"
SENT = "sent"
DELIVERED = "delivered"
READ = "read"
FAILED = "failed"
SKIPPED = "skipped"
CANCELLED = "cancelled"
DEAD_LETTER = "dead_letter"
MANUAL_REVIEW = "manual_review"

CLAIMABLE_STATUSES = {PENDING, FAILED}

PROVIDER_COMPLETED_STATUSES = {SENT, DELIVERED, READ}

FINAL_NON_RETRYABLE_STATUSES = {
    SENT,
    DELIVERED,
    READ,
    SKIPPED,
    CANCELLED,
    DEAD_LETTER,
    MANUAL_REVIEW,
}

# Failures that must never be retried automatically: reprocessing them would
# not change the outcome (bad configuration, tenant mismatch, duplicate-risk
# uncertainty) so they go straight to dead_letter instead of backoff/retry.
NON_RETRYABLE_ERROR_CODES = {
    "variable_mapping_invalid",
    "template_variable_missing",
    "template_configuration_invalid",
    "delivery_related_records_missing",
    "tenant_mismatch",
    "unsupported_delivery_action",
    "invalid_recipient",
    "whatsapp_send_precondition_failed",
    "delivery_claim_mismatch",
}
