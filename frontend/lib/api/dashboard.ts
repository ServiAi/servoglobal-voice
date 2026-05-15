export type DashboardFilters = {
  from?: string;
  to?: string;
  agent_id?: string;
  status?: string;
};

export type DashboardKpisResponse = {
  calls_total: number;
  calls_answered: number;
  calls_unanswered: number;
  answer_rate: number;
  avg_duration_seconds: number;
  total_duration_seconds: number;
  billed_minutes: number;
  active_calls: number;
};

export type DashboardTrendItem = {
  date: string;
  calls_total: number;
  calls_answered: number;
  calls_unanswered: number;
  billed_minutes: number;
  total_duration_seconds: number;
};

export type DashboardTrendsResponse = {
  series: DashboardTrendItem[];
};

export type DashboardDistributionItem = {
  key: string;
  label: string;
  calls: number;
  percentage: number;
};

export type DashboardStatusDistributionResponse = {
  items: DashboardDistributionItem[];
};

export type DashboardAgentDistributionItem = {
  agent_id: string | null;
  agent_name: string;
  calls: number;
  percentage: number;
};

export type DashboardAgentDistributionResponse = {
  items: DashboardAgentDistributionItem[];
};

export type DashboardHeatmapItem = {
  day: string;
  hour: number;
  calls: number;
};

export type DashboardHeatmapResponse = {
  matrix: DashboardHeatmapItem[];
};

export type DashboardRecentCallItem = {
  id: string;
  started_at: string;
  duration_seconds: number | null;
  billed_minutes: number | null;
  agent_name: string;
  summary: string | null;
  short_summary: string | null;
  status: string;
  external_provider: string;
};

export type DashboardRecentCallsResponse = {
  items: DashboardRecentCallItem[];
  page: number;
  page_size: number;
  total: number;
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
  return fetchDashboardEndpoint<DashboardKpisResponse>('kpis', accessToken, filters);
}

export function fetchTrends(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<DashboardTrendsResponse>('trends', accessToken, filters);
}

export function fetchStatusDistribution(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<DashboardStatusDistributionResponse>('status-distribution', accessToken, filters);
}

export function fetchAgentDistribution(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<DashboardAgentDistributionResponse>('agent-distribution', accessToken, filters);
}

export function fetchHeatmap(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<DashboardHeatmapResponse>('heatmap', accessToken, filters);
}

export function fetchRecentCalls(accessToken: string, filters?: DashboardFilters) {
  return fetchDashboardEndpoint<DashboardRecentCallsResponse>('recent-calls', accessToken, filters);
}
