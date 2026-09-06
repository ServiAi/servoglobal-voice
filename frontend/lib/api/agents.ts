import 'server-only';

import { requestAgentEndpoint } from './crm';
import type {
  AgentCreateRequest,
  AgentDraftUpdateRequest,
  AgentResponse,
  AgentUpdateRequest,
  AgentVersionResponse,
} from '@/types/agents';

export function fetchAgents(accessToken: string) {
  return requestAgentEndpoint<AgentResponse[]>('GET', '', accessToken);
}

export function fetchAgent(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentResponse>('GET', agentId, accessToken);
}

export function createAgent(accessToken: string, payload: AgentCreateRequest) {
  return requestAgentEndpoint<AgentResponse>('POST', '', accessToken, undefined, payload);
}

export function updateAgent(accessToken: string, agentId: string, payload: AgentUpdateRequest) {
  return requestAgentEndpoint<AgentResponse>('PATCH', agentId, accessToken, undefined, payload);
}

export function fetchAgentVersions(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentVersionResponse[]>('GET', `${agentId}/versions`, accessToken);
}

export function fetchAgentDraft(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentVersionResponse>('GET', `${agentId}/draft`, accessToken);
}

export function updateAgentDraft(
  accessToken: string,
  agentId: string,
  payload: AgentDraftUpdateRequest
) {
  return requestAgentEndpoint<AgentVersionResponse>(
    'PATCH',
    `${agentId}/draft`,
    accessToken,
    undefined,
    payload
  );
}

export function createAgentNextDraft(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentVersionResponse>('POST', `${agentId}/draft`, accessToken);
}

export function publishAgent(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentResponse>('POST', `${agentId}/publish`, accessToken);
}

export function archiveAgent(accessToken: string, agentId: string) {
  return requestAgentEndpoint<AgentResponse>('POST', `${agentId}/archive`, accessToken);
}
