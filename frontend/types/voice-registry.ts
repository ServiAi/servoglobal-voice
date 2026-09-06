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

export type ParameterSpecResponse = {
  supported: boolean;
  min?: number | null;
  max?: number | null;
  default?: unknown;
};

export type VoiceModelResponse = {
  id: string;
  provider_key: string;
  key: string;
  name: string;
  model_type: VoiceModelType;
  implementation_status: VoiceModelImplementationStatus;
  capabilities: Record<string, boolean>;
  parameters: Record<string, ParameterSpecResponse>;
};
