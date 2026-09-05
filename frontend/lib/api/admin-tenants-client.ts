import {
  type AgentCreatePayload,
  type FetchResult,
  type MembershipCreatePayload,
  type TenantAgent,
  type TenantCreatePayload,
  type TenantDetail,
  type TenantDeleteResult,
  type TenantListItem,
  type TenantPlanPayload,
  type TenantPlanUpdateResult,
  type TenantUpdatePayload,
} from '@/lib/api/tenants';

export type {
  AgentCreatePayload,
  FetchResult,
  MembershipCreatePayload,
  TenantAgent,
  TenantCreatePayload,
  TenantDetail,
  TenantDeleteResult,
  TenantListItem,
  TenantPlanKey,
  TenantPlanPayload,
  TenantPlanUpdateResult,
  TenantSavingsComparison,
  TenantUpdatePayload,
  TenantUsageAlert,
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

export function updateTenantPlan(
  tenantId: string,
  payload: TenantPlanPayload
): Promise<FetchResult<TenantPlanUpdateResult>> {
  return localAdminFetch<TenantPlanUpdateResult>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/plan`,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export function deleteTenant(
  tenantId: string
): Promise<FetchResult<TenantDeleteResult>> {
  return localAdminFetch<TenantDeleteResult>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}`,
    {
      method: 'DELETE',
    }
  );
}

export function addTenantMembership(
  tenantId: string,
  payload: MembershipCreatePayload
): Promise<FetchResult<TenantDetail['memberships'][number] & { password_reset_url?: string }>> {
  return localAdminFetch<TenantDetail['memberships'][number] & { password_reset_url?: string }>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/memberships`,
    {
      method: 'POST',
      body: JSON.stringify(payload),
    }
  );
}

export function sendMembershipPasswordReset(
  tenantId: string,
  membershipId: string
): Promise<FetchResult<{ success: boolean; detail: string; password_reset_url?: string }>> {
  return localAdminFetch<{ success: boolean; detail: string; password_reset_url?: string }>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/memberships/${encodeURIComponent(membershipId)}/password-reset`,
    {
      method: 'POST',
    }
  );
}

export function deleteTenantMembership(
  tenantId: string,
  membershipId: string
): Promise<FetchResult<{ deleted: boolean; membership_id: string; tenant_id: string }>> {
  return localAdminFetch<{ deleted: boolean; membership_id: string; tenant_id: string }>(
    `/api/admin/tenants/${encodeURIComponent(tenantId)}/memberships/${encodeURIComponent(membershipId)}`,
    {
      method: 'DELETE',
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
