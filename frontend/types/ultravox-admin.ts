export type UltravoxToolClassification =
  | 'provider_native'
  | 'serviglobal_supported'
  | 'unsupported_client_tool';

export type UltravoxToolSummary = {
  name: string;
  classification: UltravoxToolClassification;
};

export type UltravoxAgentSummary = {
  agent_id: string;
  published_revision_id: string | null;
  name: string;
  model: string | null;
  voice_name: string | null;
  call_count: number;
  tools: UltravoxToolSummary[];
  has_unsupported_client_tools: boolean;
};

export type UltravoxAgentPage = {
  results: UltravoxAgentSummary[];
  next_cursor: string | null;
  previous_cursor: string | null;
  total: number;
};

export type UltravoxVoiceSummary = {
  voice_id: string;
  name: string;
  language_label: string | null;
  primary_language: string | null;
  ownership: 'public' | 'private';
  billing_style: 'VOICE_BILLING_STYLE_INCLUDED' | 'VOICE_BILLING_STYLE_EXTERNAL';
  provider: string | null;
  capabilities: Record<string, boolean>;
  settings_schema: Record<string, { type: string }>;
};

export type UltravoxVoicePage = {
  results: UltravoxVoiceSummary[];
  next_cursor: string | null;
  previous_cursor: string | null;
  total: number;
};

export type UltravoxImportResponse = {
  agent_id: string;
  draft_version_id: string;
  warnings: string[];
};
