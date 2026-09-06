'use server';

import { revalidatePath } from 'next/cache';
import type { FetchResult } from '@/lib/api/crm';
import {
  archiveAgent,
  createAgent,
  createAgentNextDraft,
  fetchAgentVersions,
  publishAgent,
  updateAgent,
  updateAgentDraft,
} from '@/lib/api/agents';
import { getAccessToken } from '@/lib/auth/server';
import type {
  AgentCreateRequest,
  AgentDraftUpdateRequest,
  AgentResponse,
  AgentUpdateRequest,
  AgentVersionResponse,
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
  agentId: string
): Promise<FetchResult<AgentResponse>> {
  const result = await withAccessToken((token) => publishAgent(token, agentId));
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

export async function fetchAgentVersionsAction(
  agentId: string
): Promise<FetchResult<AgentVersionResponse[]>> {
  return withAccessToken((token) => fetchAgentVersions(token, agentId));
}
