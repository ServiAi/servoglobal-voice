import {
  type AgentCreatePayload,
  type FetchResult,
  type MembershipCreatePayload,
  type TenantAgent,
  type TenantCreatePayload,
  type TenantDetail,
  type TenantListItem,
  type TenantUpdatePayload,
} from '@/lib/api/tenants';

export type {
  AgentCreatePayload,
  FetchResult,
  MembershipCreatePayload,
  TenantAgent,
  TenantCreatePayload,
  TenantDetail,
  TenantListItem,
  TenantUpdatePayload,
} from '@/lib/api/tenants';

async function localAdminFetch<T>(
  endpoint: string,
  options?: RequestInit
): Promise<FetchResult<T>> {
  let response: Response;

  try {
    response = await fetch(endpoint, {
      ...options,
      headers: {
        ...(options?.headers ?? {}),
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
      detail =
        typeof payload.detail === 'string'
          ? payload.detail
          : JSON.stringify(payload.detail);
    } catch {
      // keep default
    }
    return { ok: false, status: response.status, detail };
  }

  const data = (await response.json()) as T;
  return { ok: true, data };
}

export function fetchTenantsList(): Promise<FetchResult<TenantListItem[]>> {
  return localAdminFetch<TenantListItem[]>('/api/admin/tenants');
}

export function fetchTenantDetail(
  tenantId: string
): Promise<FetchResult<TenantDetail>> {
  return localAdminFetch<TenantDetail>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}`
  );
}

export function createTenant(
  payload: TenantCreatePayload
): Promise<FetchResult<TenantDetail>> {
  return localAdminFetch<TenantDetail>('/api/admin/tenants', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateTenant(
  tenantId: string,
  payload: TenantUpdatePayload
): Promise<FetchResult<TenantDetail>> {
  return localAdminFetch<TenantDetail>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export function addTenantMembership(
  tenantId: string,
  payload: MembershipCreatePayload
): Promise<FetchResult<TenantDetail['memberships'][number]>> {
  return localAdminFetch<TenantDetail['memberships'][number]>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/memberships`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export function addTenantAgent(
  tenantId: string,
  payload: AgentCreatePayload
): Promise<FetchResult<TenantAgent>> {
  return localAdminFetch<TenantAgent>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/agents`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}
