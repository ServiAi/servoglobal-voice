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
  ResendTestEmailRequest,
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
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
): Promise<FetchResult<T>> {
  return requestBackendEndpoint<T>(method, 'integrations', endpoint, accessToken, queryParams, body);
}

async function requestBackendEndpoint<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  resource: 'crm' | 'integrations',
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
        ...(body ? { 'Content-Type': 'application/json' } : {}),
      },
      cache: 'no-store',
    };
    if (body) {
      config.body = JSON.stringify(body);
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
  return requestCrmEndpoint<{ message: string }>('POST', `leads/${leadId}/actions/whatsapp`, accessToken);
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

export function fetchTenantIntegrations(accessToken: string) {
  return requestIntegrationEndpoint<ResendIntegrationConfigResponse[]>('GET', '', accessToken);
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
