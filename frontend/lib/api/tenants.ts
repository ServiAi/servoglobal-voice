export type TenantListItem = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: string;
  usage?: TenantUsage;
};

export type TenantDetail = {
  id: string;
  name: string;
  slug: string;
  timezone: string;
  status: string;
  memberships: TenantMembership[];
  agents: TenantAgent[];
  usage?: TenantUsage;
  savings_comparison?: TenantSavingsComparison;
  is_ready_for_calls: boolean;
};

export type TenantPlanKey = 'web_conversion' | 'voice_cloud_pbx' | 'enterprise';

export type TenantPlanPayload = {
  plan_key: TenantPlanKey;
  included_minutes?: number;
  price_per_minute_usd?: number;
};

export type TenantPlan = {
  tenant_id: string;
  plan_key: TenantPlanKey;
  plan_name: string;
  included_minutes: number;
  price_per_minute_usd: number;
  usage_status: string;
  billing_period_start: string;
  billing_period_end: string;
  alert_thresholds: number[];
  last_usage_recalculated_at: string | null;
};

export type TenantUsageAlert = {
  id: string;
  tenant_id: string;
  alert_type: string;
  threshold_percent: number;
  billing_period_start: string;
  message: string;
  status: string;
  created_at: string;
};

export type TenantUsage = {
  tenant_id: string;
  plan: TenantPlan;
  minutes_used: number;
  minutes_remaining: number;
  usage_percent: number;
  amount_spent_usd: number;
  usage_status: string;
  alerts: TenantUsageAlert[];
};

export type SavingsComparisonProvider = {
  provider_key: string;
  provider_name: string;
  provider_price_per_minute_usd: number | null;
  price_min_per_minute_usd: number | null;
  price_max_per_minute_usd: number | null;
  price_source: string;
  source_url: string | null;
  estimated_cost_usd: number | null;
  serviglobal_cost_usd: number;
  estimated_savings_usd: number | null;
  estimated_savings_percent: number | null;
  notes: string | null;
};

export type TenantSavingsComparison = {
  tenant_id: string;
  minutes_used: number;
  serviglobal_price_per_minute_usd: number;
  serviglobal_cost_usd: number;
  providers: SavingsComparisonProvider[];
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
  plan: TenantPlanPayload;
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

export type TenantPlanUpdateResult = {
  usage: TenantUsage;
  savings_comparison: TenantSavingsComparison;
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

export type TenantDeleteResult = {
  id: string;
  slug: string;
  deleted: boolean;
  deleted_counts: Record<string, number>;
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

export function updateTenantPlan(
  accessToken: string,
  tenantId: string,
  payload: TenantPlanPayload
): Promise<FetchResult<TenantPlanUpdateResult>> {
  return adminFetch<TenantPlanUpdateResult>(
    `/api/v1/admin/tenants/${tenantId}/plan`,
    accessToken,
    {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }
  );
}

export function fetchTenantUsage(
  accessToken: string,
  tenantId: string
): Promise<FetchResult<TenantPlanUpdateResult & { alerts: TenantUsageAlert[] }>> {
  return adminFetch<TenantPlanUpdateResult & { alerts: TenantUsageAlert[] }>(
    `/api/v1/admin/tenants/${tenantId}/usage`,
    accessToken
  );
}

export function fetchUsageAlerts(
  accessToken: string
): Promise<FetchResult<TenantUsageAlert[]>> {
  return adminFetch<TenantUsageAlert[]>('/api/v1/admin/usage-alerts', accessToken);
}

export function deleteTenant(
  accessToken: string,
  tenantId: string
): Promise<FetchResult<TenantDeleteResult>> {
  return adminFetch<TenantDeleteResult>(
    `/api/v1/admin/tenants/${tenantId}`,
    accessToken,
    {
      method: 'DELETE',
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

export function sendMembershipPasswordReset(
  accessToken: string,
  tenantId: string,
  membershipId: string
): Promise<FetchResult<{ success: boolean; detail: string; password_reset_url?: string }>> {
  return adminFetch<{ success: boolean; detail: string; password_reset_url?: string }>(
    `/api/v1/admin/tenants/${tenantId}/memberships/${membershipId}/password-reset`,
    accessToken,
    {
      method: 'POST',
    }
  );
}

export function deleteTenantMembership(
  accessToken: string,
  tenantId: string,
  membershipId: string
): Promise<FetchResult<{ deleted: boolean; membership_id: string; tenant_id: string }>> {
  return adminFetch<{ deleted: boolean; membership_id: string; tenant_id: string }>(
    `/api/v1/admin/tenants/${tenantId}/memberships/${membershipId}`,
    accessToken,
    {
      method: 'DELETE',
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
