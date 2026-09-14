export type VoiceProviderStatus = 'active' | 'planned';
export type VoiceModelType = 'stt' | 'llm' | 'tts' | 'realtime';
export type VoiceModelImplementationStatus = 'planned' | 'available' | 'deprecated';

export type VoiceProviderResponse = {
  key: string;
  name: string;
  status: VoiceProviderStatus;
  supports_managed_credentials: boolean;
  supports_byok: boolean;
};

export type ParameterSpecType = 'number' | 'integer' | 'boolean' | 'string' | 'enum';

export type ParameterSpecResponse = {
  supported: boolean;
  type?: ParameterSpecType | null;
  min?: number | null;
  max?: number | null;
  step?: number | null;
  default?: unknown;
  options?: string[] | null;
  advanced?: boolean;
};

export type VoiceModelResponse = {
  id: string;
  provider_key: string;
  key: string;
  name: string;
  execution_model_id: string;
  model_type: VoiceModelType;
  implementation_status: VoiceModelImplementationStatus;
  capabilities: Record<string, boolean>;
  parameters: Record<string, ParameterSpecResponse>;
  external_voice_providers?: string[];
};
