import { requestBackendEndpoint } from './crm';
import type {
  UltravoxAgentPage,
  UltravoxAgentSummary,
  UltravoxImportResponse,
  UltravoxVoicePage,
} from '@/types/ultravox-admin';

const root = 'voice/providers/ultravox';

export function fetchUltravoxAgents(
  accessToken: string,
  query?: { cursor?: string; pageSize?: number; search?: string }
) {
  return requestBackendEndpoint<UltravoxAgentPage>('GET', 'integrations', `${root}/agents`, accessToken, query);
}

export function fetchUltravoxAgent(accessToken: string, agentId: string) {
  return requestBackendEndpoint<UltravoxAgentSummary>(
    'GET', 'integrations', `${root}/agents/${encodeURIComponent(agentId)}`, accessToken
  );
}

export function importUltravoxAgent(accessToken: string, agentId: string) {
  return requestBackendEndpoint<UltravoxImportResponse>(
    'POST',
    'integrations',
    `${root}/agents/${encodeURIComponent(agentId)}/import`,
    accessToken
  );
}

export function fetchUltravoxVoices(
  accessToken: string,
  query?: { cursor?: string; pageSize?: number; search?: string; primaryLanguage?: string }
) {
  return requestBackendEndpoint<UltravoxVoicePage>('GET', 'integrations', `${root}/voices`, accessToken, query);
}

export function ultravoxVoicePreviewUrl(voiceId: string) {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  return apiUrl
    ? `${apiUrl.replace(/\/$/, '')}/api/v1/integrations/voice/providers/ultravox/voices/${encodeURIComponent(voiceId)}/preview`
    : null;
}
