import type {
  CrmMetricsResponse,
  PipelineBoardResponse,
  LeadsListResponse,
  LeadDetailResponse,
  ActivitySchema,
  TaskResponse,
  TaskCreateRequest,
  TaskUpdateRequest,
  LeadUpdateRequest,
  StageUpdateRequest,
  NoteCreateRequest,
  CrmDashboardResponse,
  EmailActionRequest,
  EmailActionResponse,
  EmailTemplateItem,
  ResendIntegrationConfigRequest,
  ResendIntegrationConfigResponse,
  IntegrationAvailabilityResponse,
  IntegrationCatalogStatusResponse,
  ResendTestEmailRequest,
  ChatwootAgentInviteRequest,
  ChatwootAgentSummary,
  ChatwootAgentUpdateRequest,
  ChatwootConfigRequest,
  ChatwootConfigResponse,
  ChatwootInboxCreateRequest,
  ChatwootInboxSummary,
  ChatwootInboxUpdateRequest,
  ChatwootProvisionRequest,
  ChatwootTeamCreateRequest,
  ChatwootTeamSummary,
  ChatwootTeamUpdateRequest,
  ChatwootTestResponse,
  WhatsAppActionRequest,
  WhatsAppActionResponse,
  WhatsAppConfigRequest,
  WhatsAppConfigResponse,
  WhatsAppMessageResponse,
  WhatsAppTemplateResponse,
  WhatsAppTemplateSyncResponse,
  WhatsAppTestMessageRequest,
  WhatsAppTestMessageResponse,
  WhatsAppTestResponse,
  BookingConfigRequest,
  BookingConfigResponse,
  BookingCreateRequest,
  BookingResponse,
  GoogleCalendarConnectionResponse,
  GoogleCalendarConnectUrlResponse,
  TenantGoogleCalendarResponse,
  TenantGoogleCalendarUpdateRequest,
  GoogleCalendarSyncResponse,
  EmailAssetItem,
  CallSummaryAssetRequest,
  CallSummaryAssetResponse,
  CallSummaryInsertedRequest,
  CallSummaryResponse,
  TenantFormCreateRequest,
  TenantFormItem,
  FormTokenResponse,
  PublicFormResponse,
  VoiceProviderConfigRequest,
  VoiceProviderConfigResponse,
  VoiceAgentConfigRequest,
  VoiceAgentConfigResponse,
  VoiceCallActionRequest,
  VoiceCallActionResponse,
  VoiceCallResponse,
} from '@/types/crm';

export type FetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string };

function buildQueryString(paramsObj?: Record<string, unknown>): string {
  if (!paramsObj) return '';
  const params = new URLSearchParams();
  Object.entries(paramsObj).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      params.set(key, String(value));
    }
  });
  const str = params.toString();
  return str ? `?${str}` : '';
}

async function requestCrmEndpoint<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
): Promise<FetchResult<T>> {
  return requestBackendEndpoint<T>(method, 'crm', endpoint, accessToken, queryParams, body);
}

async function requestIntegrationEndpoint<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
): Promise<FetchResult<T>> {
  return requestBackendEndpoint<T>(method, 'integrations', endpoint, accessToken, queryParams, body);
}

export async function requestBackendEndpoint<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT',
  resource: 'crm' | 'integrations' | 'admin' | 'forms' | 'voice' | 'scheduling',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
): Promise<FetchResult<T>> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return { ok: false, status: 500, detail: 'Backend API URL is not configured' };
  }

  const queryStr = buildQueryString(queryParams);
  const cleanEndpoint = endpoint.replace(/^\//, '');
  const suffix = cleanEndpoint ? `/${cleanEndpoint}` : '';
  const url = `${apiUrl.replace(/\/$/, '')}/api/v1/${resource}${suffix}${queryStr}`;

  let response: Response;
  try {
    const config: RequestInit = {
      method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(body && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}),
      },
      cache: 'no-store',
    };
    if (body) {
      config.body = body instanceof FormData ? body : JSON.stringify(body);
    }
    response = await fetch(url, config);
  } catch (error) {
    console.error(`CRM API request failed for ${method} ${endpoint}`, error);
    return {
      ok: false,
      status: 502,
      detail: 'CRM API is temporarily unavailable',
    };
  }

  if (response.status === 204) {
    return { ok: true, data: null as unknown as T };
  }

  if (!response.ok) {
    let detail = `Failed to request ${endpoint}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // ignore
    }
    return { ok: false, status: response.status, detail };
  }

  let data: T;
  try {
    data = (await response.json()) as T;
  } catch (error) {
    console.error(`CRM API returned invalid JSON for ${endpoint}`, error);
    return {
      ok: false,
      status: 502,
      detail: 'CRM API returned an invalid response format',
    };
  }

  return { ok: true, data };
}

export function requestVoiceEndpoint<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
): Promise<FetchResult<T>> {
  return requestBackendEndpoint<T>(
    method,
    'voice',
    endpoint,
    accessToken,
    queryParams,
    body
  );
}

async function requestPublicBackendEndpoint<T>(
  method: 'GET' | 'POST',
  endpoint: string,
  body?: unknown
): Promise<FetchResult<T>> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return { ok: false, status: 500, detail: 'Backend API URL is not configured' };
  }
  const url = `${apiUrl.replace(/\/$/, '')}/api/v1/public/${endpoint.replace(/^\//, '')}`;
  try {
    const response = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      cache: 'no-store',
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => null);
      return { ok: false, status: response.status, detail: payload?.detail ?? `Failed to request ${endpoint}` };
    }
    return { ok: true, data: (await response.json()) as T };
  } catch {
    return { ok: false, status: 502, detail: 'CRM API is temporarily unavailable' };
  }
}

// --- Metrics ---
export function fetchCrmMetrics(
  accessToken: string,
  filters?: {
    date_from?: string;
    date_to?: string;
    source?: string;
    campaign?: string;
    assigned_agent_id?: string;
  }
) {
  return requestCrmEndpoint<CrmMetricsResponse>('GET', 'metrics', accessToken, filters);
}

// --- Dashboard ---
export function fetchCrmDashboard(
  accessToken: string,
  filters?: {
    range?: string;
    date_from?: string;
    date_to?: string;
    source?: string;
    campaign?: string;
  }
) {
  return requestCrmEndpoint<CrmDashboardResponse>('GET', 'dashboard', accessToken, filters);
}


// --- Pipeline Board ---
export function fetchCrmPipelineBoard(
  accessToken: string,
  filters?: {
    limit_per_stage?: number;
    search?: string;
    status?: string;
    source?: string;
    campaign?: string;
    assigned_agent_id?: string;
  }
) {
  return requestCrmEndpoint<PipelineBoardResponse>('GET', 'pipeline/board', accessToken, filters);
}

// --- Leads List ---
export function fetchCrmLeads(
  accessToken: string,
  filters?: {
    page?: number;
    page_size?: number;
    stage_key?: string;
    status?: string;
    search?: string;
    source?: string;
    campaign?: string;
    assigned_agent_id?: string;
    date_from?: string;
    date_to?: string;
    has_phone?: boolean;
    has_email?: boolean;
    sort_by?: string;
    sort_order?: string;
  }
) {
  return requestCrmEndpoint<LeadsListResponse>('GET', 'leads', accessToken, filters);
}

// --- Lead Detail ---
export function fetchCrmLeadDetail(accessToken: string, leadId: string) {
  return requestCrmEndpoint<LeadDetailResponse>('GET', `leads/${leadId}`, accessToken);
}

// --- Lead Update ---
export function updateCrmLead(accessToken: string, leadId: string, payload: LeadUpdateRequest) {
  return requestCrmEndpoint<LeadDetailResponse>('PATCH', `leads/${leadId}`, accessToken, undefined, payload);
}

// --- Lead Stage Change ---
export function changeCrmLeadStage(accessToken: string, leadId: string, payload: StageUpdateRequest) {
  return requestCrmEndpoint<LeadDetailResponse>('PATCH', `leads/${leadId}/stage`, accessToken, undefined, payload);
}

// --- Activities ---
export function fetchCrmActivities(
  accessToken: string,
  filters?: {
    lead_id?: string;
    contact_id?: string;
    activity_type?: string;
    date_from?: string;
    date_to?: string;
    limit?: number;
    page?: number;
  }
) {
  return requestCrmEndpoint<ActivitySchema[]>('GET', 'activities', accessToken, filters);
}

// --- Notes ---
export function createCrmLeadNote(accessToken: string, leadId: string, payload: NoteCreateRequest) {
  return requestCrmEndpoint<LeadDetailResponse>('POST', `leads/${leadId}/notes`, accessToken, undefined, payload);
}

// --- Tasks ---
export function fetchCrmTasks(
  accessToken: string,
  filters?: {
    lead_id?: string;
    contact_id?: string;
    status?: string;
    priority?: string;
  }
) {
  return requestCrmEndpoint<TaskResponse[]>('GET', 'tasks', accessToken, filters);
}

export function createCrmTask(accessToken: string, payload: TaskCreateRequest) {
  return requestCrmEndpoint<TaskResponse>('POST', 'tasks', accessToken, undefined, payload);
}

export function updateCrmTask(accessToken: string, taskId: string, payload: TaskUpdateRequest) {
  return requestCrmEndpoint<TaskResponse>('PATCH', `tasks/${taskId}`, accessToken, undefined, payload);
}

export function deleteCrmTask(accessToken: string, taskId: string) {
  return requestCrmEndpoint<void>('DELETE', `tasks/${taskId}`, accessToken);
}

// --- Lead Delete ---
export function deleteCrmLead(accessToken: string, leadId: string) {
  return requestCrmEndpoint<void>('DELETE', `leads/${leadId}`, accessToken);
}

export function deleteAllCrmLeads(accessToken: string) {
  return requestCrmEndpoint<void>('DELETE', 'leads', accessToken);
}

// --- Lead Outbound Actions ---
export function leadActionWhatsapp(accessToken: string, leadId: string) {
  return sendLeadWhatsApp(accessToken, leadId, { template_key: 'lead_follow_up' });
}

export function leadActionCall(accessToken: string, leadId: string) {
  return requestCrmEndpoint<{ message: string }>('POST', `leads/${leadId}/actions/call`, accessToken);
}

export function leadActionSchedule(accessToken: string, leadId: string) {
  return requestCrmEndpoint<{ message: string }>('POST', `leads/${leadId}/actions/schedule`, accessToken);
}

export function leadActionChatwoot(accessToken: string, leadId: string) {
  return requestCrmEndpoint<{ message: string }>('POST', `leads/${leadId}/actions/chatwoot`, accessToken);
}

export function leadActionEmail(accessToken: string, leadId: string, payload: EmailActionRequest) {
  return requestCrmEndpoint<EmailActionResponse>('POST', `leads/${leadId}/actions/email`, accessToken, undefined, payload);
}

export function previewLeadEmail(accessToken: string, leadId: string, payload: EmailActionRequest) {
  return leadActionEmail(accessToken, leadId, { ...payload, preview_only: true });
}

export function sendLeadEmail(accessToken: string, leadId: string, payload: EmailActionRequest) {
  return leadActionEmail(accessToken, leadId, { ...payload, preview_only: false });
}

export function leadActionWhatsApp(accessToken: string, leadId: string, payload: WhatsAppActionRequest) {
  return requestCrmEndpoint<WhatsAppActionResponse>('POST', `leads/${leadId}/actions/whatsapp`, accessToken, undefined, payload);
}

export function previewLeadWhatsApp(accessToken: string, leadId: string, payload: WhatsAppActionRequest) {
  return leadActionWhatsApp(accessToken, leadId, { ...payload, preview_only: true });
}

export function sendLeadWhatsApp(accessToken: string, leadId: string, payload: WhatsAppActionRequest) {
  return leadActionWhatsApp(accessToken, leadId, { ...payload, preview_only: false });
}

export function fetchLeadMessages(accessToken: string, leadId: string) {
  return requestCrmEndpoint<WhatsAppMessageResponse[]>('GET', `leads/${leadId}/messages`, accessToken);
}

export function fetchCallSummary(accessToken: string, leadId: string) {
  return requestCrmEndpoint<CallSummaryResponse>('GET', `leads/${leadId}/call-summary`, accessToken);
}

export function recordCallSummaryInserted(accessToken: string, leadId: string, payload: CallSummaryInsertedRequest) {
  return requestCrmEndpoint<void>('POST', `leads/${leadId}/call-summary/inserted`, accessToken, undefined, payload);
}

export function createCallSummaryAsset(accessToken: string, leadId: string, payload: CallSummaryAssetRequest) {
  return requestCrmEndpoint<CallSummaryAssetResponse>('POST', `leads/${leadId}/call-summary/asset`, accessToken, undefined, payload);
}

export function fetchLeadBookings(accessToken: string, leadId: string) {
  return requestCrmEndpoint<BookingResponse[]>('GET', `leads/${leadId}/bookings`, accessToken);
}

export function createLeadBooking(accessToken: string, leadId: string, payload: BookingCreateRequest) {
  return requestCrmEndpoint<BookingResponse>('POST', `leads/${leadId}/bookings`, accessToken, undefined, payload);
}

export function cancelLeadBooking(accessToken: string, leadId: string, bookingId: string) {
  return requestCrmEndpoint<void>('POST', `leads/${leadId}/bookings/${bookingId}/cancel`, accessToken);
}

export function rescheduleLeadBooking(
  accessToken: string,
  leadId: string,
  bookingId: string,
  payload: { new_start_time: string; new_end_time: string }
) {
  return requestCrmEndpoint<void>('POST', `leads/${leadId}/bookings/${bookingId}/reschedule`, accessToken, undefined, payload);
}

export function fetchTenantIntegrations(accessToken: string) {
  return requestIntegrationEndpoint<ResendIntegrationConfigResponse[]>('GET', '', accessToken);
}

export function fetchIntegrationAvailability(accessToken: string) {
  return requestIntegrationEndpoint<IntegrationAvailabilityResponse[]>('GET', 'availability', accessToken);
}

export function fetchIntegrationCatalogStatuses(accessToken: string) {
  return requestIntegrationEndpoint<IntegrationCatalogStatusResponse[]>('GET', 'statuses', accessToken);
}

export function fetchBookingConfig(accessToken: string) {
  return requestIntegrationEndpoint<BookingConfigResponse>('GET', 'booking/config', accessToken);
}

export function fetchWhatsAppConfig(accessToken: string) {
  return requestIntegrationEndpoint<WhatsAppConfigResponse>('GET', 'whatsapp/config', accessToken);
}

export function configureWhatsAppIntegration(accessToken: string, payload: WhatsAppConfigRequest) {
  return requestIntegrationEndpoint<WhatsAppConfigResponse>('POST', 'whatsapp/config', accessToken, undefined, payload);
}

export function testWhatsAppIntegration(accessToken: string) {
  return requestIntegrationEndpoint<WhatsAppTestResponse>('POST', 'whatsapp/test', accessToken);
}

export function fetchWhatsAppTemplates(accessToken: string) {
  return requestIntegrationEndpoint<WhatsAppTemplateResponse[]>('GET', 'whatsapp/templates', accessToken);
}

export function syncWhatsAppTemplates(accessToken: string) {
  return requestIntegrationEndpoint<WhatsAppTemplateSyncResponse>('POST', 'whatsapp/templates/sync', accessToken);
}

export function sendWhatsAppTestMessage(accessToken: string, payload: WhatsAppTestMessageRequest) {
  return requestIntegrationEndpoint<WhatsAppTestMessageResponse>(
    'POST', 'whatsapp/test-message', accessToken, undefined, payload
  );
}

export function configureCalComIntegration(accessToken: string, payload: BookingConfigRequest) {
  return requestIntegrationEndpoint<BookingConfigResponse>('POST', 'calcom/config', accessToken, undefined, payload);
}

export function testCalComIntegration(accessToken: string) {
  return requestIntegrationEndpoint<{ status: string; error_message?: string | null }>('POST', 'calcom/test', accessToken);
}

export function fetchCalComSlots(accessToken: string, params: { date: string; jornada?: string; reference_datetime?: string }) {
  return requestIntegrationEndpoint<{
    date: string;
    jornada: string;
    available_slots: Array<{ start: string }>;
    summary: string;
  }>('GET', 'calcom/slots', accessToken, params);
}

export function fetchGoogleCalendarConnections(accessToken: string) {
  return requestIntegrationEndpoint<GoogleCalendarConnectionResponse[]>('GET', 'google-calendar/connections', accessToken);
}

export function fetchGoogleCalendarConnectUrl(accessToken: string) {
  return requestIntegrationEndpoint<GoogleCalendarConnectUrlResponse>('GET', 'google-calendar/connect-url', accessToken);
}

export function disconnectGoogleCalendar(accessToken: string, connectionId: string) {
  return requestIntegrationEndpoint<GoogleCalendarConnectionResponse>(
    'POST',
    'google-calendar/disconnect',
    accessToken,
    { connection_id: connectionId }
  );
}

export function deleteGoogleCalendarConnection(accessToken: string, connectionId: string) {
  return requestIntegrationEndpoint<{ deleted: boolean; connection_id: string }>(
    'DELETE',
    `google-calendar/connections/${connectionId}`,
    accessToken
  );
}

export function syncGoogleCalendarConnection(accessToken: string, connectionId: string) {
  return requestIntegrationEndpoint<GoogleCalendarSyncResponse>(
    'POST',
    `google-calendar/connections/${connectionId}/sync`,
    accessToken
  );
}

export function fetchGoogleCalendars(accessToken: string, connectionId?: string) {
  return requestIntegrationEndpoint<TenantGoogleCalendarResponse[]>(
    'GET',
    'google-calendar/calendars',
    accessToken,
    connectionId ? { connection_id: connectionId } : undefined
  );
}

export function updateGoogleCalendar(
  accessToken: string,
  calendarId: string,
  payload: TenantGoogleCalendarUpdateRequest
) {
  return requestIntegrationEndpoint<TenantGoogleCalendarResponse>(
    'PATCH',
    `google-calendar/calendars/${calendarId}`,
    accessToken,
    undefined,
    payload
  );
}

export function fetchChatwootConfig(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootConfigResponse>('GET', 'chatwoot/config', accessToken);
}

export function configureChatwootIntegration(accessToken: string, payload: ChatwootConfigRequest) {
  return requestIntegrationEndpoint<ChatwootConfigResponse>('POST', 'chatwoot/config', accessToken, undefined, payload);
}

export function testChatwootIntegration(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootTestResponse>('POST', 'chatwoot/test', accessToken);
}

export function provisionChatwootIntegration(accessToken: string, payload: ChatwootProvisionRequest) {
  return requestIntegrationEndpoint<ChatwootConfigResponse>('POST', 'chatwoot/provision', accessToken, undefined, payload);
}

export function disconnectChatwootIntegration(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootConfigResponse>('POST', 'chatwoot/disconnect', accessToken);
}

export function fetchAdminTenantChatwootConfig(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootConfigResponse>(
    'GET', 'admin', `tenants/${tenantId}/integrations/chatwoot/config`, accessToken
  );
}

export function configureAdminTenantChatwoot(
  accessToken: string,
  tenantId: string,
  payload: ChatwootConfigRequest
) {
  return requestBackendEndpoint<ChatwootConfigResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/config`, accessToken, undefined, payload
  );
}

export function testAdminTenantChatwoot(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootTestResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/test`, accessToken
  );
}

export function provisionAdminTenantChatwoot(
  accessToken: string,
  tenantId: string,
  payload: ChatwootProvisionRequest
) {
  return requestBackendEndpoint<ChatwootConfigResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/provision`, accessToken, undefined, payload
  );
}

export function fetchChatwootInboxes(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootInboxSummary[]>('GET', 'chatwoot/inboxes', accessToken);
}

export function fetchChatwootTeams(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootTeamSummary[]>('GET', 'chatwoot/teams', accessToken);
}

export function fetchAdminTenantChatwootInboxes(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootInboxSummary[]>(
    'GET', 'admin', `tenants/${tenantId}/integrations/chatwoot/inboxes`, accessToken
  );
}

export function fetchAdminTenantChatwootTeams(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootTeamSummary[]>(
    'GET', 'admin', `tenants/${tenantId}/integrations/chatwoot/teams`, accessToken
  );
}

export function disconnectAdminTenantChatwoot(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootConfigResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/disconnect`, accessToken
  );
}

export function createChatwootInbox(accessToken: string, payload: ChatwootInboxCreateRequest) {
  return requestIntegrationEndpoint<ChatwootInboxSummary>('POST', 'chatwoot/inboxes', accessToken, undefined, payload);
}

export function createAdminTenantChatwootInbox(accessToken: string, tenantId: string, payload: ChatwootInboxCreateRequest) {
  return requestBackendEndpoint<ChatwootInboxSummary>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/inboxes`, accessToken, undefined, payload
  );
}

export function createChatwootTeam(accessToken: string, payload: ChatwootTeamCreateRequest) {
  return requestIntegrationEndpoint<ChatwootTeamSummary>('POST', 'chatwoot/teams', accessToken, undefined, payload);
}

export function createAdminTenantChatwootTeam(accessToken: string, tenantId: string, payload: ChatwootTeamCreateRequest) {
  return requestBackendEndpoint<ChatwootTeamSummary>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/teams`, accessToken, undefined, payload
  );
}

export function fetchChatwootAgents(accessToken: string) {
  return requestIntegrationEndpoint<ChatwootAgentSummary[]>('GET', 'chatwoot/agents', accessToken);
}

export function fetchAdminTenantChatwootAgents(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ChatwootAgentSummary[]>(
    'GET', 'admin', `tenants/${tenantId}/integrations/chatwoot/agents`, accessToken
  );
}

export function inviteChatwootAgent(accessToken: string, payload: ChatwootAgentInviteRequest) {
  return requestIntegrationEndpoint<ChatwootAgentSummary>('POST', 'chatwoot/agents', accessToken, undefined, payload);
}

export function inviteAdminTenantChatwootAgent(accessToken: string, tenantId: string, payload: ChatwootAgentInviteRequest) {
  return requestBackendEndpoint<ChatwootAgentSummary>(
    'POST', 'admin', `tenants/${tenantId}/integrations/chatwoot/agents`, accessToken, undefined, payload
  );
}

export function updateChatwootInbox(accessToken: string, inboxId: number, payload: ChatwootInboxUpdateRequest) {
  return requestIntegrationEndpoint<ChatwootInboxSummary>('PATCH', `chatwoot/inboxes/${inboxId}`, accessToken, undefined, payload);
}

export function updateAdminTenantChatwootInbox(accessToken: string, tenantId: string, inboxId: number, payload: ChatwootInboxUpdateRequest) {
  return requestBackendEndpoint<ChatwootInboxSummary>(
    'PATCH', 'admin', `tenants/${tenantId}/integrations/chatwoot/inboxes/${inboxId}`, accessToken, undefined, payload
  );
}

export function updateChatwootTeam(accessToken: string, teamId: number, payload: ChatwootTeamUpdateRequest) {
  return requestIntegrationEndpoint<ChatwootTeamSummary>('PATCH', `chatwoot/teams/${teamId}`, accessToken, undefined, payload);
}

export function updateAdminTenantChatwootTeam(accessToken: string, tenantId: string, teamId: number, payload: ChatwootTeamUpdateRequest) {
  return requestBackendEndpoint<ChatwootTeamSummary>(
    'PATCH', 'admin', `tenants/${tenantId}/integrations/chatwoot/teams/${teamId}`, accessToken, undefined, payload
  );
}

export function deleteChatwootTeam(accessToken: string, teamId: number) {
  return requestIntegrationEndpoint<null>('DELETE', `chatwoot/teams/${teamId}`, accessToken);
}

export function deleteAdminTenantChatwootTeam(accessToken: string, tenantId: string, teamId: number) {
  return requestBackendEndpoint<null>('DELETE', 'admin', `tenants/${tenantId}/integrations/chatwoot/teams/${teamId}`, accessToken);
}

export function updateChatwootAgent(accessToken: string, agentId: number, payload: ChatwootAgentUpdateRequest) {
  return requestIntegrationEndpoint<ChatwootAgentSummary>('PATCH', `chatwoot/agents/${agentId}`, accessToken, undefined, payload);
}

export function updateAdminTenantChatwootAgent(accessToken: string, tenantId: string, agentId: number, payload: ChatwootAgentUpdateRequest) {
  return requestBackendEndpoint<ChatwootAgentSummary>(
    'PATCH', 'admin', `tenants/${tenantId}/integrations/chatwoot/agents/${agentId}`, accessToken, undefined, payload
  );
}

export function deleteChatwootAgent(accessToken: string, agentId: number) {
  return requestIntegrationEndpoint<null>('DELETE', `chatwoot/agents/${agentId}`, accessToken);
}

export function deleteAdminTenantChatwootAgent(accessToken: string, tenantId: string, agentId: number) {
  return requestBackendEndpoint<null>('DELETE', 'admin', `tenants/${tenantId}/integrations/chatwoot/agents/${agentId}`, accessToken);
}

export function configureResendIntegration(accessToken: string, payload: ResendIntegrationConfigRequest) {
  return requestIntegrationEndpoint<ResendIntegrationConfigResponse>('POST', 'resend/config', accessToken, undefined, payload);
}

export function testResendIntegration(accessToken: string, payload: ResendTestEmailRequest) {
  return requestIntegrationEndpoint<{ status: string; provider_email_id?: string | null }>(
    'POST',
    'resend/test',
    accessToken,
    undefined,
    payload
  );
}

export function fetchResendTemplates(accessToken: string) {
  return requestIntegrationEndpoint<EmailTemplateItem[]>('GET', 'resend/templates', accessToken);
}

export function fetchEmailAssets(accessToken: string) {
  return requestIntegrationEndpoint<EmailAssetItem[]>('GET', 'resend/assets', accessToken);
}

export function uploadEmailAsset(accessToken: string, file: File) {
  const body = new FormData();
  body.set('file', file);
  return requestIntegrationEndpoint<EmailAssetItem>('POST', 'resend/assets', accessToken, undefined, body);
}

export function deleteEmailAsset(accessToken: string, assetId: string) {
  return requestIntegrationEndpoint<void>('DELETE', `resend/assets/${assetId}`, accessToken);
}

export function fetchTenantForms(accessToken: string) {
  return requestBackendEndpoint<TenantFormItem[]>('GET', 'forms', '', accessToken);
}

export function createTenantForm(accessToken: string, payload: TenantFormCreateRequest) {
  return requestBackendEndpoint<TenantFormItem>('POST', 'forms', '', accessToken, undefined, payload);
}

export function createLeadFormToken(accessToken: string, formId: string, leadId: string, expiresInDays = 7) {
  return requestBackendEndpoint<FormTokenResponse>(
    'POST',
    'forms',
    `${formId}/tokens`,
    accessToken,
    undefined,
    { lead_id: leadId, expires_in_days: expiresInDays }
  );
}

export function fetchAdminTenantIntegrations(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<ResendIntegrationConfigResponse[]>(
    'GET',
    'admin',
    `tenants/${tenantId}/integrations`,
    accessToken
  );
}

export function fetchAdminTenantIntegrationAvailability(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<IntegrationAvailabilityResponse[]>(
    'GET',
    'admin',
    `tenants/${tenantId}/integrations/availability`,
    accessToken
  );
}

export function fetchAdminTenantIntegrationStatuses(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<IntegrationCatalogStatusResponse[]>(
    'GET',
    'admin',
    `tenants/${tenantId}/integrations/statuses`,
    accessToken
  );
}

export function updateAdminTenantIntegrationAvailability(
  accessToken: string,
  tenantId: string,
  provider: IntegrationAvailabilityResponse['provider'],
  enabled: boolean
) {
  return requestBackendEndpoint<IntegrationAvailabilityResponse>(
    'PATCH',
    'admin',
    `tenants/${tenantId}/integrations/availability/${provider}`,
    accessToken,
    undefined,
    { enabled }
  );
}

export function fetchAdminTenantBookingConfig(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<BookingConfigResponse>('GET', 'admin', `tenants/${tenantId}/integrations/booking/config`, accessToken);
}

export function fetchAdminTenantWhatsAppConfig(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<WhatsAppConfigResponse>('GET', 'admin', `tenants/${tenantId}/integrations/whatsapp/config`, accessToken);
}

export function configureAdminTenantCalComIntegration(accessToken: string, tenantId: string, payload: BookingConfigRequest) {
  return requestBackendEndpoint<BookingConfigResponse>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/calcom/config`,
    accessToken,
    undefined,
    payload
  );
}

export function testAdminTenantCalComIntegration(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<{ status: string; error_message?: string | null }>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/calcom/test`,
    accessToken
  );
}

export function fetchAdminTenantGoogleCalendarConnections(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<GoogleCalendarConnectionResponse[]>(
    'GET',
    'admin',
    `tenants/${tenantId}/integrations/google-calendar/connections`,
    accessToken
  );
}

export function deleteAdminTenantGoogleCalendarConnection(
  accessToken: string,
  tenantId: string,
  connectionId: string
) {
  return requestBackendEndpoint<{ deleted: boolean; connection_id: string; tenant_id: string }>(
    'DELETE',
    'admin',
    `tenants/${tenantId}/integrations/google-calendar/connections/${connectionId}`,
    accessToken
  );
}

export function configureAdminTenantResendIntegration(
  accessToken: string,
  tenantId: string,
  payload: ResendIntegrationConfigRequest
) {
  return requestBackendEndpoint<ResendIntegrationConfigResponse>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/resend/config`,
    accessToken,
    undefined,
    payload
  );
}

export function testAdminTenantResendIntegration(
  accessToken: string,
  tenantId: string,
  payload: ResendTestEmailRequest
) {
  return requestBackendEndpoint<{ status: string; provider_email_id?: string | null }>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/resend/test`,
    accessToken,
    undefined,
    payload
  );
}

export function configureAdminTenantWhatsAppIntegration(
  accessToken: string,
  tenantId: string,
  payload: WhatsAppConfigRequest
) {
  return requestBackendEndpoint<WhatsAppConfigResponse>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/whatsapp/config`,
    accessToken,
    undefined,
    payload
  );
}

export function testAdminTenantWhatsAppIntegration(
  accessToken: string,
  tenantId: string
) {
  return requestBackendEndpoint<WhatsAppTestResponse>(
    'POST',
    'admin',
    `tenants/${tenantId}/integrations/whatsapp/test`,
    accessToken
  );
}

export function fetchAdminTenantWhatsAppTemplates(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<WhatsAppTemplateResponse[]>(
    'GET',
    'admin',
    `tenants/${tenantId}/integrations/whatsapp/templates`,
    accessToken
  );
}

export function syncAdminTenantWhatsAppTemplates(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<WhatsAppTemplateSyncResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/whatsapp/templates/sync`, accessToken
  );
}

export function sendAdminTenantWhatsAppTestMessage(
  accessToken: string,
  tenantId: string,
  payload: WhatsAppTestMessageRequest
) {
  return requestBackendEndpoint<WhatsAppTestMessageResponse>(
    'POST', 'admin', `tenants/${tenantId}/integrations/whatsapp/test-message`, accessToken, undefined, payload
  );
}

export function fetchAdminTenantForms(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<TenantFormItem[]>('GET', 'admin', `tenants/${tenantId}/forms`, accessToken);
}

export function createAdminTenantForm(accessToken: string, tenantId: string, payload: TenantFormCreateRequest) {
  return requestBackendEndpoint<TenantFormItem>('POST', 'admin', `tenants/${tenantId}/forms`, accessToken, undefined, payload);
}

export function createAdminLeadFormToken(accessToken: string, tenantId: string, formId: string, leadId: string, expiresInDays = 7) {
  return requestBackendEndpoint<FormTokenResponse>(
    'POST',
    'admin',
    `tenants/${tenantId}/forms/${formId}/tokens`,
    accessToken,
    undefined,
    { lead_id: leadId, expires_in_days: expiresInDays }
  );
}

export function fetchAdminTenantEmailAssets(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<EmailAssetItem[]>('GET', 'admin', `tenants/${tenantId}/integrations/resend/assets`, accessToken);
}

export function uploadAdminTenantEmailAsset(accessToken: string, tenantId: string, file: File) {
  const body = new FormData();
  body.set('file', file);
  return requestBackendEndpoint<EmailAssetItem>('POST', 'admin', `tenants/${tenantId}/integrations/resend/assets`, accessToken, undefined, body);
}

export function deleteAdminTenantEmailAsset(accessToken: string, tenantId: string, assetId: string) {
  return requestBackendEndpoint<void>('DELETE', 'admin', `tenants/${tenantId}/integrations/resend/assets/${assetId}`, accessToken);
}

export function fetchPublicForm(token: string) {
  return requestPublicBackendEndpoint<PublicFormResponse>('GET', `forms/${token}`);
}

export function submitPublicForm(token: string, answers: Record<string, string | boolean | null>, hp?: string) {
  return requestPublicBackendEndpoint<{ status: string; submission_id: string }>('POST', `forms/${token}/submit`, {
    answers,
    hp,
  });
}


// --- CRM Voice ---

export function startCrmLeadVoiceCall(accessToken: string, leadId: string, payload: VoiceCallActionRequest) {
  return requestCrmEndpoint<VoiceCallActionResponse>('POST', `leads/${leadId}/actions/call`, accessToken, undefined, payload);
}

export function fetchCrmLeadVoiceCalls(accessToken: string, leadId: string) {
  return requestCrmEndpoint<VoiceCallResponse[]>('GET', `leads/${leadId}/calls`, accessToken);
}


// --- Voice Integration Config ---

export function fetchVoiceConfig(accessToken: string) {
  return requestIntegrationEndpoint<VoiceProviderConfigResponse>('GET', 'voice/config', accessToken);
}

export function configureVoice(accessToken: string, payload: VoiceProviderConfigRequest) {
  return requestIntegrationEndpoint<VoiceProviderConfigResponse>('POST', 'voice/config', accessToken, undefined, payload);
}

export function testVoiceConnection(accessToken: string) {
  return requestIntegrationEndpoint<{ status: string }>('POST', 'voice/test', accessToken);
}


// --- Voice Agent Config ---

export function fetchVoiceAgents(accessToken: string) {
  return requestIntegrationEndpoint<VoiceAgentConfigResponse[]>('GET', 'voice/agents', accessToken);
}

export function createVoiceAgent(accessToken: string, payload: VoiceAgentConfigRequest) {
  return requestIntegrationEndpoint<VoiceAgentConfigResponse>('POST', 'voice/agents', accessToken, undefined, payload);
}

export function updateVoiceAgent(accessToken: string, agentConfigId: string, payload: VoiceAgentConfigRequest) {
  return requestIntegrationEndpoint<VoiceAgentConfigResponse>('PUT', `voice/agents/${agentConfigId}`, accessToken, undefined, payload);
}


// --- Admin Voice Integrations ---

export function fetchAdminTenantVoiceConfig(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<VoiceProviderConfigResponse>('GET', 'admin', `tenants/${tenantId}/integrations/voice/config`, accessToken);
}

export function configureAdminTenantVoice(accessToken: string, tenantId: string, payload: VoiceProviderConfigRequest) {
  return requestBackendEndpoint<VoiceProviderConfigResponse>('POST', 'admin', `tenants/${tenantId}/integrations/voice/config`, accessToken, undefined, payload);
}

export function testAdminTenantVoice(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<{ status: string }>('POST', 'admin', `tenants/${tenantId}/integrations/voice/test`, accessToken);
}

export function fetchAdminTenantVoiceAgents(accessToken: string, tenantId: string) {
  return requestBackendEndpoint<VoiceAgentConfigResponse[]>('GET', 'admin', `tenants/${tenantId}/integrations/voice/agents`, accessToken);
}

export function createAdminTenantVoiceAgent(accessToken: string, tenantId: string, payload: VoiceAgentConfigRequest) {
  return requestBackendEndpoint<VoiceAgentConfigResponse>('POST', 'admin', `tenants/${tenantId}/integrations/voice/agents`, accessToken, undefined, payload);
}

export function updateAdminTenantVoiceAgent(accessToken: string, tenantId: string, agentConfigId: string, payload: VoiceAgentConfigRequest) {
  return requestBackendEndpoint<VoiceAgentConfigResponse>('PATCH', 'admin', `tenants/${tenantId}/integrations/voice/agents/${agentConfigId}`, accessToken, undefined, payload);
}
