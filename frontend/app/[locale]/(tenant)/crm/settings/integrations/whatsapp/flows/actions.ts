'use server';

import { getAccessToken } from '@/lib/auth/server';
import type { FetchResult } from '@/lib/api/crm';
import {
  cloneWhatsAppFlow,
  compileWhatsAppFlow,
  createWhatsAppFlow,
  deleteWhatsAppFlow,
  deprecateWhatsAppFlow,
  publishWhatsAppFlow,
  syncWhatsAppFlowMeta,
  syncWhatsAppFlowStatus,
  updateWhatsAppFlow,
} from '@/lib/api/whatsapp-flows';
import type {
  WhatsAppFlow,
  WhatsAppFlowCompileResponse,
  WhatsAppFlowCreateRequest,
  WhatsAppFlowUpdateRequest,
} from '@/types/whatsapp-flows';

async function authenticated<T>(run: (token: string) => Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  const token = await getAccessToken();
  return token ? run(token) : { ok: false, status: 401, detail: 'unauthorized' };
}

export const createWhatsAppFlowAction = async (payload: WhatsAppFlowCreateRequest) =>
  authenticated<WhatsAppFlow>((token) => createWhatsAppFlow(token, payload));
export const updateWhatsAppFlowAction = async (flowId: string, payload: WhatsAppFlowUpdateRequest) =>
  authenticated<WhatsAppFlow>((token) => updateWhatsAppFlow(token, flowId, payload));
export const deleteWhatsAppFlowAction = async (flowId: string) =>
  authenticated<null>((token) => deleteWhatsAppFlow(token, flowId));
export const compileWhatsAppFlowAction = async (flowId: string) =>
  authenticated<WhatsAppFlowCompileResponse>((token) => compileWhatsAppFlow(token, flowId));
export const syncWhatsAppFlowMetaAction = async (flowId: string) =>
  authenticated<WhatsAppFlow>((token) => syncWhatsAppFlowMeta(token, flowId));
export const syncWhatsAppFlowStatusAction = async (flowId: string) =>
  authenticated<WhatsAppFlow>((token) => syncWhatsAppFlowStatus(token, flowId));
export const publishWhatsAppFlowAction = async (flowId: string) =>
  authenticated<WhatsAppFlow>((token) => publishWhatsAppFlow(token, flowId));
export const cloneWhatsAppFlowAction = async (flowId: string) =>
  authenticated<WhatsAppFlow>((token) => cloneWhatsAppFlow(token, flowId));
export const deprecateWhatsAppFlowAction = async (flowId: string) =>
  authenticated<WhatsAppFlow>((token) => deprecateWhatsAppFlow(token, flowId));
