'use server';

import { getAccessToken } from '@/lib/auth/server';
import type { FetchResult } from '@/lib/api/crm';
import {
  activateCustomTool,
  createCustomTool,
  deleteCustomTool,
  disableCustomTool,
  testCustomTool,
  updateCustomTool,
} from '@/lib/api/tools-custom';
import type {
  CustomToolCreateRequest,
  CustomToolResponse,
  CustomToolTestRequest,
  CustomToolTestResponse,
  CustomToolUpdateRequest,
} from '@/types/tools-custom';

async function withAccessToken<T>(run: (accessToken: string) => Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    return { ok: false, status: 401, detail: 'unauthorized' };
  }
  return run(accessToken);
}

export async function createCustomToolAction(
  payload: CustomToolCreateRequest
): Promise<FetchResult<CustomToolResponse>> {
  return withAccessToken((accessToken) => createCustomTool(accessToken, payload));
}

export async function updateCustomToolAction(
  toolId: string,
  payload: CustomToolUpdateRequest
): Promise<FetchResult<CustomToolResponse>> {
  return withAccessToken((accessToken) => updateCustomTool(accessToken, toolId, payload));
}

export async function deleteCustomToolAction(toolId: string): Promise<FetchResult<null>> {
  return withAccessToken((accessToken) => deleteCustomTool(accessToken, toolId));
}

export async function activateCustomToolAction(toolId: string): Promise<FetchResult<CustomToolResponse>> {
  return withAccessToken((accessToken) => activateCustomTool(accessToken, toolId));
}

export async function disableCustomToolAction(toolId: string): Promise<FetchResult<CustomToolResponse>> {
  return withAccessToken((accessToken) => disableCustomTool(accessToken, toolId));
}

export async function testCustomToolAction(
  toolId: string,
  payload: CustomToolTestRequest
): Promise<FetchResult<CustomToolTestResponse>> {
  return withAccessToken((accessToken) => testCustomTool(accessToken, toolId, payload));
}
