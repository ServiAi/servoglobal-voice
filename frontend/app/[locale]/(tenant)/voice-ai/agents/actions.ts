'use server';

import { revalidatePath } from 'next/cache';
import { fetchCrmLeads, requestVoiceEndpoint, type FetchResult } from '@/lib/api/crm';
import type { LeadListItem } from '@/types/crm';
import {
  archiveAgent,
  createAgent,
  createAgentNextDraft,
  deleteAgent,
  fetchAgentVersions,
  publishAgent,
  unpublishAgent,
  updateAgent,
  updateAgentDraft,
} from '@/lib/api/agents';
import { previewExternalVoiceAudio, previewProviderVoiceAudio, type VoicePreviewResult } from '@/lib/api/voice-preview';
import { getAccessToken } from '@/lib/auth/server';
import type {
  AgentCreateRequest,
  AgentDraftUpdateRequest,
  AgentResponse,
  AgentUpdateRequest,
  AgentVersionResponse,
  AgentVoiceConfig,
} from '@/types/agents';

async function withAccessToken<T>(
  run: (accessToken: string) => Promise<FetchResult<T>>
): Promise<FetchResult<T>> {
  const accessToken = await getAccessToken();
  if (!accessToken) return { ok: false, status: 401, detail: 'unauthorized' };
  return run(accessToken);
}

function revalidateAgents(locale: string, agentId?: string) {
  revalidatePath(`/${locale}/voice-ai/agents`, 'layout');
  if (agentId) revalidatePath(`/${locale}/voice-ai/agents/${agentId}`, 'layout');
}

export async function createAgentAction(
  locale: string,
  payload: AgentCreateRequest
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) => createAgent(token, payload));
  if (result.ok) revalidateAgents(locale);
  return result;
}

export async function updateAgentAction(
  locale: string,
  agentId: string,
  payload: AgentUpdateRequest
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) => updateAgent(token, agentId, payload));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function updateAgentDraftAction(
  locale: string,
  agentId: string,
  payload: AgentDraftUpdateRequest
): Promise<FetchResult<AgentVersionResponse>> {
  const result = await withAccessToken((token) => updateAgentDraft(token, agentId, payload));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function createAgentNextDraftAction(
  locale: string,
  agentId: string
): Promise<FetchResult<AgentVersionResponse>> {
  const result = await withAccessToken((token) => createAgentNextDraft(token, agentId));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function publishAgentAction(
  locale: string,
  agentId: string,
  expectedDraftVersionId?: string
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) =>
    publishAgent(token, agentId, { expected_draft_version_id: expectedDraftVersionId })
  );
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function archiveAgentAction(
  locale: string,
  agentId: string
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) => archiveAgent(token, agentId));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function unpublishAgentAction(
  locale: string,
  agentId: string
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) => unpublishAgent(token, agentId));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function deleteAgentAction(
  locale: string,
  agentId: string
): Promise<FetchResult<null>> {
  const result = await withAccessToken((token) => deleteAgent(token, agentId));
  if (result.ok) revalidateAgents(locale, agentId);
  return result;
}

export async function fetchAgentVersionsAction(
  agentId: string
): Promise<FetchResult<AgentVersionResponse[]>> {
  return withAccessToken((token) => fetchAgentVersions(token, agentId));
}

export type VoiceSessionResponse = {
  id: string;
  status: string;
  purpose: 'production' | 'qa';
  channel: 'webrtc' | 'sip' | 'internal_test';
  direction: 'internal' | 'outbound';
  agent_version_id: string | null;
  provider: string;
  runtime_engine: string;
  pipeline_type: string;
  error_code: string | null;
  end_reason: string | null;
  livekit_room_name: string | null;
};

export type VoiceQaSessionInput = {
  transport: 'webrtc' | 'sip';
  caller_phone?: string;
  contact_id?: string;
  lead_id?: string;
  to_phone?: string;
  variables?: Record<string, unknown>;
};

export type VoiceQaEvent = {
  event_id: string;
  event_type: string;
  source: string;
  sequence: number | null;
  payload: Record<string, string | number | boolean | null>;
  occurred_at: string;
};

export type VoiceQaEventsResponse = {
  session: VoiceSessionResponse;
  context: {
    caller_phone: string | null;
    contact_id: string | null;
    lead_id: string | null;
    variables: Record<string, unknown>;
  };
  events: VoiceQaEvent[];
};

export type WebRTCParticipantTokenResponse = {
  voice_session_id: string;
  server_url: string;
  room_name: string;
  participant_token: string;
  expires_in: number;
};

export async function createVoiceTestSessionAction(
  agentId: string,
  idempotencyKey: string,
  input: VoiceQaSessionInput = { transport: 'webrtc' }
): Promise<FetchResult<VoiceSessionResponse>> {
  return withAccessToken((token) =>
    requestVoiceEndpoint<VoiceSessionResponse>('POST', 'sessions', token, undefined, {
      agent_id: agentId,
      channel: input.transport,
      direction: input.transport === 'sip' ? 'outbound' : 'internal',
      purpose: 'qa',
      idempotency_key: idempotencyKey,
      caller_phone: input.caller_phone || undefined,
      contact_id: input.contact_id || undefined,
      lead_id: input.lead_id || undefined,
      to_phone: input.transport === 'sip' ? input.to_phone : undefined,
      variables: input.variables ?? {},
    })
  );
}

export async function fetchVoiceQaLeadsAction(search: string): Promise<FetchResult<LeadListItem[]>> {
  return withAccessToken(async (token) => {
    const result = await fetchCrmLeads(token, { page: 1, page_size: 20, search: search || undefined });
    return result.ok ? { ...result, data: result.data.items } : result;
  });
}

export async function fetchVoiceTestEventsAction(
  sessionId: string
): Promise<FetchResult<VoiceQaEventsResponse>> {
  return withAccessToken((token) =>
    requestVoiceEndpoint<VoiceQaEventsResponse>('GET', `sessions/${sessionId}/events`, token)
  );
}

export async function previewProviderVoiceAction(
  provider: string,
  voiceId: string
): Promise<VoicePreviewResult> {
  const accessToken = await getAccessToken();
  if (!accessToken) return { ok: false, status: 401, code: 'provider_auth_failed' };
  return previewProviderVoiceAudio(accessToken, provider, voiceId);
}

export async function previewExternalVoiceAction(
  provider: string,
  voice: AgentVoiceConfig
): Promise<VoicePreviewResult> {
  const accessToken = await getAccessToken();
  if (!accessToken) return { ok: false, status: 401, code: 'provider_auth_failed' };
  return previewExternalVoiceAudio(accessToken, provider, voice);
}

export async function createVoiceTestTokenAction(
  sessionId: string
): Promise<FetchResult<WebRTCParticipantTokenResponse>> {
  return withAccessToken((token) =>
    requestVoiceEndpoint<WebRTCParticipantTokenResponse>(
      'POST',
      `sessions/${sessionId}/webrtc-token`,
      token
    )
  );
}
