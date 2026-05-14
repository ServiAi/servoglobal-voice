export type DashboardFilters = {
  from?: string;
  to?: string;
  agent_id?: string;
  status?: string;
};

export type KpiData = {
  total_calls: number;
  total_minutes: number;
  avg_duration_seconds: number;
  avg_cost: number;
  success_rate: number;
};

export type TrendPoint = {
  date: string;
  total_calls: number;
  success_rate: number;
};

export type StatusDistribution = {
  status: string;
  count: number;
};

export type AgentDistribution = {
  agent_name: string;
  count: number;
};

export type HeatmapPoint = {
  day_of_week: number;
  hour_of_day: number;
  call_count: number;
};

export type RecentCall = {
  id: string;
  created_at: string;
  duration_seconds: number;
  status: string;
  agent_name: string;
  cost: number;
};

export type FetchResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; detail: string };

function buildQueryString(filters?: DashboardFilters): string {
  if (!filters) return '';
  const params = new URLSearchParams();
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  if (filters.agent_id) params.set('agent_id', filters.agent_id);
  if (filters.status) params.set('status', filters.status);
  
  const str = params.toString();
  return str ? `?${str}` : '';
}

async function fetchDashboardEndpoint<T>(
  endpoint: string,
  accessToken: string,
  filters?: DashboardFilters
): Promise<FetchResult<T>> {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL;
  if (!apiUrl) {
    return { ok: false, status: 500, detail: 'Backend API URL is not configured' };
  }

  const queryStr = buildQueryString(filters);
  const url = `${apiUrl.replace(/\/$/, '')}/api/v1/dashboard/${endpoint}${queryStr}`;

  const response = await fetch(url, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
    // We shouldn't cache dashboard data strictly, but we can revalidate.
    // Given the need for up-to-date data, 'no-store' is safest.
    cache: 'no-store',
  });

  if (!response.ok) {
    let detail = `Failed to fetch ${endpoint}`;
    try {
      const payload = await response.json();
      detail = payload.detail ?? detail;
    } catch {
      // Keep default error
    }
    return { ok: false, status: response.status, detail };
  }

  const data = await response.json();
  return { ok: true, data };
}

export function fetchKpis(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<KpiData>('kpis', accessToken, filters);
}

export function fetchTrends(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<TrendPoint[]>('trends', accessToken, filters);
}

export function fetchStatusDistribution(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<StatusDistribution[]>('status-distribution', accessToken, filters);
}

export function fetchAgentDistribution(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<AgentDistribution[]>('agent-distribution', accessToken, filters);
}

export function fetchHeatmap(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<HeatmapPoint[]>('heatmap', accessToken, filters);
}

export function fetchRecentCalls(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<RecentCall[]>('recent-calls', accessToken, filters);
}
