export type AgentStatus = 'draft' | 'active' | 'archived';
export type AgentVersionStatus = 'draft' | 'published' | 'superseded';
export type AgentResponseStyle = 'precise' | 'balanced' | 'creative';
export type AgentInterruptions = 'conservative' | 'balanced' | 'responsive';
export type AgentTurnDetection = 'automatic' | 'conservative' | 'balanced' | 'responsive';
export type AgentConfirmationStrategy = 'important_data' | 'always' | 'never';

export type AgentIdentity = {
  name: string;
  description?: string | null;
};

export type AgentInstructions = {
  role: string;
  objective: string;
  system_prompt: string;
  greeting: string;
  closing: string;
};

export type AgentBehavior = {
  response_style: AgentResponseStyle;
  interruptions: AgentInterruptions;
  turn_detection: AgentTurnDetection;
  confirmation_strategy: AgentConfirmationStrategy;
  agent_first: boolean;
};

/** Provider/model runtime parameters (e.g. temperature). Which keys are
 * valid for a given (provider, model) comes from VoiceModelResponse.parameters
 * (see types/voice-registry.ts) -- this type is intentionally a generic bag,
 * never hardcoded to one provider. */
export type AgentModelSettings = Record<string, number | boolean | string>;

/** A tool bound to a serviglobal_managed agent version. `config` is
 * binding-time configuration (currently unused by both V1 tools -- kept
 * for forward compatibility), never the per-call arguments the LLM
 * supplies at invocation time. */
export type AgentToolBinding = {
  key: string;
  enabled: boolean;
  config?: Record<string, never>;
};

/** One app.domain.tool_registry entry annotated for the current tenant --
 * see GET /api/v1/agents/tools/catalog. `available` is only ever true for
 * status="available" tools whose required_integration is configured;
 * "planned" tools always report available=false and must never be
 * offered as selectable in the UI. */
export type AgentToolCatalogEntry = {
  key: string;
  name: string;
  description: string;
  status: 'available' | 'planned';
  required_integration: 'booking' | 'whatsapp' | 'crm' | 'chatwoot' | null;
  available: boolean;
  input_schema: Record<string, unknown>;
};

export type AgentCreateRequest = {
  name: string;
  description?: string | null;
  language: string;
  timezone: string;
  instructions: AgentInstructions;
  behavior: AgentBehavior;
  voice_agent_config_id?: string | null;
  pipeline_type: 'realtime';
  provider: string;
  model: string;
  management_mode?: 'serviglobal_managed' | 'provider_managed';
  provider_agent?: ProviderAgentReference | null;
  voice?: AgentVoiceConfig | null;
  settings?: AgentModelSettings | Record<string, never>;
  tools?: AgentToolBinding[];
};

export type ProviderAgentReference = {
  agent_id: string;
  observed_published_revision_id?: string | null;
};

/** ElevenLabs is the only provider_external target with a real adapter in
 * V1 (see backend voice_registry.py); the settings keys below are exactly
 * the allowlist VoiceSelectionService enforces server-side. `model` is a
 * free string by design -- no closed enum, see Phase D decisions. */
export type ExternalVoiceSettings = {
  model?: string;
  speed?: number;
  stability?: number;
  similarity_boost?: number;
  use_speaker_boost?: boolean;
};

export type AgentVoiceConfig = {
  mode: 'provider' | 'provider_external';
  provider: string;
  voice_id: string;
  settings?: ExternalVoiceSettings | Record<string, never>;
};

export type AgentUpdateRequest = {
  name: string;
  description?: string | null;
};

export type AgentDraftUpdateRequest = {
  name: string;
  description?: string | null;
  language: string;
  timezone: string;
  instructions: AgentInstructions;
  behavior: AgentBehavior;
  voice_agent_config_id?: string | null;
  pipeline_type: 'realtime';
  provider: string;
  model: string;
  management_mode?: 'serviglobal_managed' | 'provider_managed';
  provider_agent?: ProviderAgentReference | null;
  voice?: AgentVoiceConfig | null;
  settings?: AgentModelSettings | Record<string, never>;
  tools?: AgentToolBinding[];
};

export type AgentPublishRequest = {
  expected_draft_version_id?: string | null;
};

export type AgentResponse = {
  id: string;
  name: string;
  description: string | null;
  status: AgentStatus;
  published_version_id: string | null;
  draft_version_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type AgentRuntimeBinding = {
  pipeline_type: 'realtime';
  realtime: {
    provider: string;
    model: string;
    management_mode?: 'serviglobal_managed' | 'provider_managed';
    provider_agent?: ProviderAgentReference | null;
    voice?: AgentVoiceConfig | null;
    settings?: AgentModelSettings | Record<string, never>;
    provider_extensions?: {
      observed_revision_drift?: boolean;
      tools?: Array<{ name: string; classification: string }>;
      warnings?: string[];
    };
  };
  // Top-level, sibling of `realtime` -- never nested inside it, so it can
  // never collide with the unrelated realtime.provider_extensions.tools
  // (a read-only classification of an imported provider_managed agent's
  // own remote tools).
  tools?: AgentToolBinding[];
};

export type AgentVersionResponse = {
  id: string;
  agent_id: string;
  version: number;
  status: AgentVersionStatus;
  language: string;
  timezone: string;
  identity: AgentIdentity;
  instructions: AgentInstructions;
  behavior: AgentBehavior;
  runtime_binding: AgentRuntimeBinding;
  voice_agent_config_id: string | null;
  published_at: string | null;
  created_at: string;
};

export type AgentGateState = 'ok' | 'feature_disabled' | 'access_denied' | 'error';
