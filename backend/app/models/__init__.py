from app.models.analytics import Agent, Call, CallEvent, MetricSnapshotDaily
from app.models.billing import (
    ExternalProviderPricing,
    TenantBillingPlan,
    TenantUsageAlert,
)
from app.models.identity import AccessAuditLog, Tenant, TenantMembership, User
from app.models.integrations import (  # noqa: F401  (residual: Forms + Voice config)
    TenantVoiceAgentConfig,
    TenantVoiceProviderConfig,
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
from app.models.tenant_features import TenantFeatureGrant
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
