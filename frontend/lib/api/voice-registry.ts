import 'server-only';

import { requestVoiceEndpoint } from './crm';
import type { VoiceModelResponse, VoiceProviderResponse } from '@/types/voice-registry';

export function fetchVoiceProviders(accessToken: string) {
  return requestVoiceEndpoint<VoiceProviderResponse[]>('GET', 'providers', accessToken);
}

export function fetchVoiceModels(accessToken: string, queryParams?: { type?: string; provider?: string }) {
  return requestVoiceEndpoint<VoiceModelResponse[]>('GET', 'models', accessToken, queryParams);
}
