import { requestBackendEndpoint } from './crm';
import type {
  AgentSchedulingConfig,
  SchedulingAvailabilityException,
  SchedulingDashboardSummary,
  SchedulingResource,
  SchedulingResourceCalendar,
  SchedulingTeam,
  SchedulingTeamMember,
  TenantSchedulingConfig,
} from '@/types/scheduling';

function schedulingApi<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE' | 'PUT',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
) {
  return requestBackendEndpoint<T>(
    method,
    'scheduling',
    endpoint,
    accessToken,
    queryParams,
    body
  );
}

// Config & Summary
export function fetchSchedulingSummary(accessToken: string) {
  return schedulingApi<SchedulingDashboardSummary>('GET', 'dashboard/summary', accessToken);
}

export function fetchSchedulingConfig(accessToken: string) {
  return schedulingApi<TenantSchedulingConfig>('GET', 'config', accessToken);
}

export function updateSchedulingConfig(accessToken: string, payload: Partial<TenantSchedulingConfig>) {
  return schedulingApi<TenantSchedulingConfig>('PUT', 'config', accessToken, undefined, payload);
}

// Resources
export function fetchSchedulingResources(accessToken: string, team?: string) {
  return schedulingApi<SchedulingResource[]>('GET', 'resources', accessToken, team ? { team } : undefined);
}

export function createSchedulingResource(accessToken: string, payload: Partial<SchedulingResource>) {
  return schedulingApi<SchedulingResource>('POST', 'resources', accessToken, undefined, payload);
}

export function updateSchedulingResource(accessToken: string, resourceId: string, payload: Partial<SchedulingResource>) {
  return schedulingApi<SchedulingResource>('PUT', `resources/${resourceId}`, accessToken, undefined, payload);
}

export function deleteSchedulingResource(accessToken: string, resourceId: string) {
  return schedulingApi<{ status: string }>('DELETE', `resources/${resourceId}`, accessToken);
}

export function updateResourceAvailability(accessToken: string, resourceId: string, workingHours: Record<string, unknown>) {
  return schedulingApi<SchedulingResource>('PUT', `resources/${resourceId}/availability`, accessToken, undefined, workingHours);
}

export function assignCalendarToResource(accessToken: string, resourceId: string, payload: { calendar_id: string; is_blocking: boolean; is_destination: boolean }) {
  return schedulingApi<SchedulingResourceCalendar>('POST', `resources/${resourceId}/calendars`, accessToken, undefined, payload);
}

// Teams
export function fetchSchedulingTeams(accessToken: string) {
  return schedulingApi<SchedulingTeam[]>('GET', 'teams', accessToken);
}

export function createSchedulingTeam(accessToken: string, payload: Partial<SchedulingTeam>) {
  return schedulingApi<SchedulingTeam>('POST', 'teams', accessToken, undefined, payload);
}

export function updateSchedulingTeam(accessToken: string, teamId: string, payload: Partial<SchedulingTeam>) {
  return schedulingApi<SchedulingTeam>('PUT', `teams/${teamId}`, accessToken, undefined, payload);
}

export function deleteSchedulingTeam(accessToken: string, teamId: string) {
  return schedulingApi<{ status: string }>('DELETE', `teams/${teamId}`, accessToken);
}

export function addSchedulingTeamMember(accessToken: string, teamId: string, payload: { resource_id: string; priority?: number; is_active?: boolean }) {
  return schedulingApi<SchedulingTeamMember>('POST', `teams/${teamId}/members`, accessToken, undefined, payload);
}

export function removeSchedulingTeamMember(accessToken: string, teamId: string, resourceId: string) {
  return schedulingApi<{ status: string }>('DELETE', `teams/${teamId}/members/${resourceId}`, accessToken);
}

// Exceptions
export function fetchSchedulingExceptions(accessToken: string, resourceId?: string) {
  return schedulingApi<SchedulingAvailabilityException[]>('GET', 'exceptions', accessToken, resourceId ? { resource_id: resourceId } : undefined);
}

export function createSchedulingException(accessToken: string, payload: Partial<SchedulingAvailabilityException>) {
  return schedulingApi<SchedulingAvailabilityException>('POST', 'exceptions', accessToken, undefined, payload);
}

export function deleteSchedulingException(accessToken: string, exceptionId: string) {
  return schedulingApi<{ status: string }>('DELETE', `exceptions/${exceptionId}`, accessToken);
}

// Agents
export function fetchAgentSchedulingConfig(accessToken: string, agentId: string) {
  return schedulingApi<AgentSchedulingConfig>('GET', `agents/${agentId}`, accessToken);
}

export function upsertAgentSchedulingConfig(accessToken: string, agentId: string, payload: Partial<AgentSchedulingConfig>) {
  return schedulingApi<AgentSchedulingConfig>('PUT', `agents/${agentId}`, accessToken, undefined, payload);
}
