import 'server-only';

import { requestBackendEndpoint } from './crm';
import type {
  CustomToolCreateRequest,
  CustomToolResponse,
  CustomToolTestRequest,
  CustomToolTestResponse,
  CustomToolUpdateRequest,
} from '@/types/tools-custom';

function toolsCustom<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  body?: unknown
) {
  return requestBackendEndpoint<T>(
    method,
    'tools',
    endpoint ? `custom/${endpoint}` : 'custom',
    accessToken,
    undefined,
    body
  );
}

export function fetchCustomTools(accessToken: string) {
  return toolsCustom<CustomToolResponse[]>('GET', '', accessToken);
}

export function fetchCustomTool(accessToken: string, toolId: string) {
  return toolsCustom<CustomToolResponse>('GET', toolId, accessToken);
}

export function createCustomTool(accessToken: string, payload: CustomToolCreateRequest) {
  return toolsCustom<CustomToolResponse>('POST', '', accessToken, payload);
}

export function updateCustomTool(accessToken: string, toolId: string, payload: CustomToolUpdateRequest) {
  return toolsCustom<CustomToolResponse>('PATCH', toolId, accessToken, payload);
}

export function deleteCustomTool(accessToken: string, toolId: string) {
  return toolsCustom<null>('DELETE', toolId, accessToken);
}

export function activateCustomTool(accessToken: string, toolId: string) {
  return toolsCustom<CustomToolResponse>('POST', `${toolId}/activate`, accessToken);
}

export function disableCustomTool(accessToken: string, toolId: string) {
  return toolsCustom<CustomToolResponse>('POST', `${toolId}/disable`, accessToken);
}

export function testCustomTool(accessToken: string, toolId: string, payload: CustomToolTestRequest) {
  return toolsCustom<CustomToolTestResponse>('POST', `${toolId}/test`, accessToken, payload);
}
