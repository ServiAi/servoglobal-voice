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
};

export type AgentUpdateRequest = {
  name: string;
  description?: string | null;
};

export type AgentDraftUpdateRequest = {
  language: string;
  timezone: string;
  instructions: AgentInstructions;
  behavior: AgentBehavior;
  voice_agent_config_id?: string | null;
  pipeline_type: 'realtime';
  provider: string;
  model: string;
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
  realtime: { provider: string; model: string };
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
