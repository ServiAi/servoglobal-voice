import 'server-only';

import { requestBackendEndpoint } from './crm';
import type {
  WhatsAppFlow,
  WhatsAppFlowCompileResponse,
  WhatsAppFlowCreateRequest,
  WhatsAppFlowUpdateRequest,
} from '@/types/whatsapp-flows';

function flows<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  body?: unknown
) {
  return requestBackendEndpoint<T>(
    method,
    'integrations',
    `whatsapp/flows${endpoint}`,
    accessToken,
    undefined,
    body
  );
}

export const fetchWhatsAppFlows = (accessToken: string) => flows<WhatsAppFlow[]>('GET', '', accessToken);
export const fetchWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('GET', `/${flowId}`, accessToken);
export const createWhatsAppFlow = (accessToken: string, payload: WhatsAppFlowCreateRequest) =>
  flows<WhatsAppFlow>('POST', '', accessToken, payload);
export const updateWhatsAppFlow = (accessToken: string, flowId: string, payload: WhatsAppFlowUpdateRequest) =>
  flows<WhatsAppFlow>('PATCH', `/${flowId}`, accessToken, payload);
export const deleteWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<null>('DELETE', `/${flowId}`, accessToken);
export const compileWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlowCompileResponse>('POST', `/${flowId}/compile`, accessToken);
export const syncWhatsAppFlowMeta = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('POST', `/${flowId}/sync-meta`, accessToken);
export const syncWhatsAppFlowStatus = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('POST', `/${flowId}/sync-status`, accessToken);
export const publishWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('POST', `/${flowId}/publish`, accessToken);
export const cloneWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('POST', `/${flowId}/clone`, accessToken);
export const deprecateWhatsAppFlow = (accessToken: string, flowId: string) =>
  flows<WhatsAppFlow>('POST', `/${flowId}/deprecate`, accessToken);
