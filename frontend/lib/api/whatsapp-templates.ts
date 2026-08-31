import { requestBackendEndpoint } from './crm';
import type {
  WhatsAppTemplateCreateRequest,
  WhatsAppTemplateDetailResponse,
  WhatsAppTemplatePreviewResponse,
  WhatsAppTemplateSubmitResponse,
  WhatsAppTemplateUpdateRequest,
} from '@/types/crm';

function whatsappTemplates<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  body?: unknown
) {
  return requestBackendEndpoint<T>(method, 'integrations', `whatsapp/templates${endpoint}`, accessToken, undefined, body);
}

function adminWhatsappTemplates<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  tenantId: string,
  endpoint: string,
  accessToken: string,
  body?: unknown
) {
  return requestBackendEndpoint<T>(
    method,
    'admin',
    `tenants/${tenantId}/integrations/whatsapp/templates${endpoint}`,
    accessToken,
    undefined,
    body
  );
}

export function createWhatsAppTemplate(accessToken: string, payload: WhatsAppTemplateCreateRequest) {
  return whatsappTemplates<WhatsAppTemplateDetailResponse>('POST', '', accessToken, payload);
}

export function fetchWhatsAppTemplateDetail(accessToken: string, templateId: string) {
  return whatsappTemplates<WhatsAppTemplateDetailResponse>('GET', `/${templateId}`, accessToken);
}

export function updateWhatsAppTemplate(
  accessToken: string,
  templateId: string,
  payload: WhatsAppTemplateUpdateRequest
) {
  return whatsappTemplates<WhatsAppTemplateDetailResponse>('PATCH', `/${templateId}`, accessToken, payload);
}

export function deleteWhatsAppTemplate(accessToken: string, templateId: string) {
  return whatsappTemplates<null>('DELETE', `/${templateId}`, accessToken);
}

export function previewWhatsAppTemplate(accessToken: string, templateId: string) {
  return whatsappTemplates<WhatsAppTemplatePreviewResponse>('GET', `/${templateId}/preview`, accessToken);
}

export function submitWhatsAppTemplate(accessToken: string, templateId: string) {
  return whatsappTemplates<WhatsAppTemplateSubmitResponse>('POST', `/${templateId}/submit`, accessToken);
}

export function syncWhatsAppTemplateStatus(accessToken: string, templateId: string) {
  return whatsappTemplates<WhatsAppTemplateSubmitResponse>('POST', `/${templateId}/sync-status`, accessToken);
}

export function createAdminTenantWhatsAppTemplate(
  accessToken: string,
  tenantId: string,
  payload: WhatsAppTemplateCreateRequest
) {
  return adminWhatsappTemplates<WhatsAppTemplateDetailResponse>('POST', tenantId, '', accessToken, payload);
}

export function fetchAdminTenantWhatsAppTemplateDetail(accessToken: string, tenantId: string, templateId: string) {
  return adminWhatsappTemplates<WhatsAppTemplateDetailResponse>('GET', tenantId, `/${templateId}`, accessToken);
}

export function updateAdminTenantWhatsAppTemplate(
  accessToken: string,
  tenantId: string,
  templateId: string,
  payload: WhatsAppTemplateUpdateRequest
) {
  return adminWhatsappTemplates<WhatsAppTemplateDetailResponse>('PATCH', tenantId, `/${templateId}`, accessToken, payload);
}

export function deleteAdminTenantWhatsAppTemplate(accessToken: string, tenantId: string, templateId: string) {
  return adminWhatsappTemplates<null>('DELETE', tenantId, `/${templateId}`, accessToken);
}

export function previewAdminTenantWhatsAppTemplate(accessToken: string, tenantId: string, templateId: string) {
  return adminWhatsappTemplates<WhatsAppTemplatePreviewResponse>('GET', tenantId, `/${templateId}/preview`, accessToken);
}

export function submitAdminTenantWhatsAppTemplate(accessToken: string, tenantId: string, templateId: string) {
  return adminWhatsappTemplates<WhatsAppTemplateSubmitResponse>('POST', tenantId, `/${templateId}/submit`, accessToken);
}

export function syncAdminTenantWhatsAppTemplateStatus(accessToken: string, tenantId: string, templateId: string) {
  return adminWhatsappTemplates<WhatsAppTemplateSubmitResponse>(
    'POST',
    tenantId,
    `/${templateId}/sync-status`,
    accessToken
  );
}
