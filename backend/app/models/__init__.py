from app.modules.analytics.infrastructure.models import Agent, Call, CallEvent, MetricSnapshotDaily
from app.modules.billing.infrastructure.models import (
    ExternalProviderPricing,
    TenantBillingPlan,
    TenantUsageAlert,
)
from app.models.integrations import (  # noqa: F401  (residual: Forms + Voice config)
    TenantVoiceAgentConfig,
    TenantVoiceProviderConfig,
)
from app.models.voice_context import TenantVoiceContextField, TenantVoiceContextSchema
from app.models.voice_experiences import (
    TenantVoiceExperience,
    TenantVoiceExperienceVersion,
)
from app.models.voice_submissions import (
    TenantVoiceContextSession,
    TenantVoiceExperienceSubmission,
    TenantVoiceExperienceSubmissionValue,
    TenantVoiceRuntimeCall,
    VoicePublicRateLimitWindow,
)
from app.modules.agents.infrastructure.models import TenantAgent, TenantAgentVersion
from app.modules.crm.infrastructure.models import (
    CrmActivity,
    CrmCallContext,
    CrmContact,
    CrmLead,
    CrmPipelineStage,
    CrmTask,
    CrmVoiceCall,
    CrmVoiceCallEvent,
)
from app.modules.identity.infrastructure.models import (
    AccessAuditLog,
    Tenant,
    TenantFeatureGrant,
    TenantMembership,
    User,
)
from app.modules.integrations.infrastructure.models import (  # noqa: F401  (registers the tables)
    CrmWhatsAppMessage,
    TenantChatwootConfig,
    TenantChatwootInbox,
    TenantEmailAsset,
    TenantEmailConfig,
    TenantEmailSend,
    TenantEmailSendAsset,
    TenantEmailTemplate,
    TenantIntegration,
    TenantIntegrationEvent,
    TenantWhatsAppConfig,
    TenantWhatsAppFlow,
    TenantWhatsAppTemplate,
)
from app.modules.notifications.infrastructure.models import (
    DomainEvent,
    NotificationDelivery,
    TenantCapability,
    TenantNotificationRecipient,
    TenantNotificationRule,
)
from app.modules.scheduling.infrastructure.models import (  # noqa: F401  (registers the tables)
    CrmBooking,
    CrmBookingEvent,
    TenantAgentSchedulingConfig,
    TenantBookingConfig,
    TenantGoogleCalendar,
    TenantGoogleCalendarConnection,
    TenantSchedulingAvailabilityException,
    TenantSchedulingConfig,
    TenantSchedulingEventType,
    TenantSchedulingProviderObject,
    TenantSchedulingResource,
    TenantSchedulingResourceCalendar,
    TenantSchedulingSchedule,
    TenantSchedulingTeam,
    TenantSchedulingTeamMember,
    TenantVoiceBookingConfig,
)
from app.modules.telephony.infrastructure.models import TenantSipRoute
from app.modules.tools.infrastructure.models import (
    TenantHttpToolConfig,
    TenantTool,
    TenantToolCredential,
)
from app.modules.voice.infrastructure.models import VoiceSession, VoiceSessionEvent
from app.modules.evaluations.infrastructure.models import (
    CriterionResult,
    EvaluationDefinition,
    EvaluationDefinitionVersion,
    EvaluationRun,
)

__all__ = [
    "AccessAuditLog",
    "Agent",
    "TenantAgent",
    "TenantAgentVersion",
    "Call",
    "CallEvent",
    "ExternalProviderPricing",
    "MetricSnapshotDaily",
    "Tenant",
    "TenantBillingPlan",
    "TenantEmailAsset",
    "TenantEmailConfig",
    "TenantEmailSend",
    "TenantEmailTemplate",
    "TenantIntegration",
    "TenantIntegrationEvent",
    "TenantFeatureGrant",
    "TenantTool",
    "TenantHttpToolConfig",
    "TenantToolCredential",
    "TenantVoiceProviderConfig",
    "TenantVoiceAgentConfig",
    "TenantVoiceContextField",
    "TenantVoiceContextSchema",
    "TenantVoiceExperience",
    "TenantVoiceExperienceVersion",
    "TenantVoiceExperienceSubmission",
    "TenantVoiceExperienceSubmissionValue",
    "TenantVoiceContextSession",
    "TenantVoiceRuntimeCall",
    "VoicePublicRateLimitWindow",
    "VoiceSession",
    "VoiceSessionEvent",
    "TenantWhatsAppConfig",
    "TenantWhatsAppFlow",
    "TenantWhatsAppTemplate",
    "TenantMembership",
    "TenantUsageAlert",
    "User",
    "CrmContact",
    "CrmPipelineStage",
    "CrmLead",
    "CrmActivity",
    "CrmCallContext",
    "CrmTask",
    "CrmVoiceCall",
    "CrmVoiceCallEvent",
    "CrmWhatsAppMessage",
]
