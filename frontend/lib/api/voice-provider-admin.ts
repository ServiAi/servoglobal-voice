import { requestBackendEndpoint } from './crm';
import type {
  UltravoxAgentPage,
  UltravoxAgentSummary,
  UltravoxImportResponse,
  UltravoxVoicePage,
} from '@/types/ultravox-admin';

function root(provider: string) {
  return `voice/providers/${provider}`;
}

export function fetchProviderAgents(
  accessToken: string,
  provider: string,
  query?: { cursor?: string; pageSize?: number; search?: string }
) {
  return requestBackendEndpoint<UltravoxAgentPage>('GET', 'integrations', `${root(provider)}/agents`, accessToken, query);
}

export function fetchProviderAgent(accessToken: string, provider: string, agentId: string) {
  return requestBackendEndpoint<UltravoxAgentSummary>(
    'GET', 'integrations', `${root(provider)}/agents/${encodeURIComponent(agentId)}`, accessToken
  );
}

export function importProviderAgent(accessToken: string, provider: string, agentId: string) {
  return requestBackendEndpoint<UltravoxImportResponse>(
    'POST',
    'integrations',
    `${root(provider)}/agents/${encodeURIComponent(agentId)}/import`,
    accessToken
  );
}

export function fetchProviderVoices(
  accessToken: string,
  provider: string,
  query?: { cursor?: string; pageSize?: number; search?: string; primaryLanguage?: string }
) {
  return requestBackendEndpoint<UltravoxVoicePage>('GET', 'integrations', `${root(provider)}/voices`, accessToken, query);
}

export function providerVoicePreviewUrl(provider: string, voiceId: string) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  return apiUrl
    ? `${apiUrl.replace(/\/$/, '')}/api/v1/integrations/voice/providers/${provider}/voices/${encodeURIComponent(voiceId)}/preview`
    : null;
}
