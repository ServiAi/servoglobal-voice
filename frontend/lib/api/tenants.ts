export type TenantListItem = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: string;
};

export type TenantDetail = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: string;
  memberships: TenantMembership[];
  agents: TenantAgent[];
  is_ready_for_calls: boolean;
};

export type TenantMembership = {
  id: string;
  tenant_id: string;
  user_id: string;
  role: string;
  status: string;
  user_email: string | null;
  user_name: string | null;
};

export type TenantAgent = {
  id: string;
  tenant_id: string;
  name: string;
  external_provider: string;
  external_agent_id: string;
  channel_type: string | null;
  status: string;
};

export type TenantCreatePayload = {
  name: string;
  slug: string;
  timezone: string;
  status: string;
  admin: {
    name: string;
    email: string;
    role: string;
  };
  agents: Array<{
    name: string;
    external_provider: string;
    external_agent_id: string;
    channel_type?: string;
    status?: string;
  }>;
};

export type TenantUpdatePayload = {
  name?: string;
  timezone?: string;
  status?: string;
};

export type MembershipCreatePayload = {
  email: string;
  role?: string;
};

export type AgentCreatePayload = {
  name: string;
  external_provider: string;
  external_agent_id: string;
  channel_type?: string;
  status?: string;
};

export type FetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string };

async function adminFetch<T>(
  endpoint: string,
  accessToken: string,
  options?: RequestInit
): Promise<FetchResult<T>> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return { ok: false, status: 500, detail: 'Backend API URL is not configured' };
  }

  const url = `${apiUrl.replace(/\/$/, '')}${endpoint}`;

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      headers: {
        ...(options?.headers ?? {}),
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      cache: 'no-store',
    });
  } catch {
    return { ok: false, status: 502, detail: 'API is temporarily unavailable' };
  }

  if (!response.ok) {
    let detail = `Request failed with status ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // keep default
    }
    return { ok: false, status: response.status, detail };
  }

  const data = (await response.json()) as T;
  return { ok: true, data };
}

export function fetchTenantsList(accessToken: string): Promise<FetchResult<TenantListItem[]>> {
  return adminFetch<TenantListItem[]>('/api/v1/admin/tenants', accessToken);
}

export function fetchTenantDetail(
  accessToken: string,
  tenantId: string
): Promise<FetchResult<TenantDetail>> {
  return adminFetch<TenantDetail>(`/api/v1/admin/tenants/${tenantId}`, accessToken);
}

export function createTenant(
  accessToken: string,
  payload: TenantCreatePayload
): Promise<FetchResult<TenantDetail>> {
  return adminFetch<TenantDetail>(
    '/api/v1/admin/tenants',
    accessToken,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export function updateTenant(
  accessToken: string,
  tenantId: string,
  payload: TenantUpdatePayload
): Promise<FetchResult<TenantDetail>> {
  return adminFetch<TenantDetail>(
    `/api/v1/admin/tenants/${tenantId}`,
    accessToken,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export function addTenantMembership(
  accessToken: string,
  tenantId: string,
  payload: MembershipCreatePayload
): Promise<FetchResult<TenantMembership>> {
  return adminFetch<TenantMembership>(
    `/api/v1/admin/tenants/${tenantId}/memberships`,
    accessToken,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export function addTenantAgent(
  accessToken: string,
  tenantId: string,
  payload: AgentCreatePayload
): Promise<FetchResult<TenantAgent>> {
  return adminFetch<TenantAgent>(
    `/api/v1/admin/tenants/${tenantId}/agents`,
    accessToken,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}
