export type VoiceExperienceStatus = 'draft' | 'published' | 'unpublished' | 'archived';
export type VoiceExperienceLayout = 'centered' | 'split' | 'card';
export type VoiceContextSchemaStatus = 'draft' | 'active' | 'archived';
export type VoiceContextFieldType =
  | 'text'
  | 'textarea'
  | 'email'
  | 'phone'
  | 'integer'
  | 'select'
  | 'checkbox'
  | 'date';
export type VoiceContextCollectionMode =
  | 'ask_if_missing'
  | 'prefill_and_confirm'
  | 'trust_prefill'
  | 'internal_only'
  | 'collect_during_call';
export type VoiceContextSensitivity = 'standard' | 'sensitive';

export type VoiceExperienceContent = {
  title: string;
  description: string;
  submit_label: string;
  call_label: string;
  success_message: string;
};

export type VoiceExperienceTheme = {
  logo_url?: string | null;
  primary_color?: string | null;
  layout: VoiceExperienceLayout;
};

export type VoiceExperienceConsent = {
  required: boolean;
  label?: string | null;
  privacy_url?: string | null;
};

export type VoiceExperienceCallSettings = {
  auto_start: boolean;
  show_microphone_help: boolean;
  language: string;
};

export type VoiceExperienceWriteRequest = {
  agent_config_id: string;
  context_schema_id: string;
  name: string;
  default_locale: string;
  content: VoiceExperienceContent;
  theme: VoiceExperienceTheme;
  consent: VoiceExperienceConsent;
  call_settings: VoiceExperienceCallSettings;
};

export type VoiceExperienceResponse = VoiceExperienceWriteRequest & {
  id: string;
  slug: string;
  status: VoiceExperienceStatus;
  published_version_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
};

export type VoiceExperienceVersionResponse = VoiceExperienceWriteRequest & {
  id: string;
  experience_id: string;
  version: number;
  slug: string;
  published_at: string;
  created_at: string;
};

export type VoiceContextFieldOption = {
  value: string;
  label: string;
};

export type VoiceContextFieldRequest = {
  key: string;
  label: string;
  description?: string | null;
  field_type: VoiceContextFieldType;
  collection_mode: VoiceContextCollectionMode;
  required: boolean;
  position: number;
  sensitivity: VoiceContextSensitivity;
  validation_json: Record<string, unknown>;
  options_json: VoiceContextFieldOption[];
};

export type VoiceContextFieldResponse = VoiceContextFieldRequest & {
  id: string;
};

export type VoiceContextSchemaCreateRequest = {
  schema_key: string;
  name: string;
  description?: string | null;
};

export type VoiceContextSchemaMetaUpdateRequest = {
  name: string;
  description?: string | null;
};

export type VoiceContextSchemaResponse = {
  id: string;
  agent_config_id: string;
  schema_key: string;
  version: number;
  status: VoiceContextSchemaStatus;
  name: string;
  description?: string | null;
  fields: VoiceContextFieldResponse[];
  created_at: string;
  updated_at: string;
  activated_at: string | null;
  archived_at: string | null;
};

export type VoiceContextSchemaSummaryResponse = {
  id: string;
  agent_config_id: string;
  schema_key: string;
  version: number;
  status: VoiceContextSchemaStatus;
  name: string;
  field_count: number;
  updated_at: string;
};

export type VoiceExperienceGateState =
  | 'ok'
  | 'feature_disabled'
  | 'integration_disabled'
  | 'no_agents'
  | 'access_denied'
  | 'error';
