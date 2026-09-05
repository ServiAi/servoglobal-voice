import { requestBackendEndpoint } from './crm';
import type {
  AgentSchedulingConfig,
  CalComDiscoveryResponse,
  SchedulingAvailabilityException,
  SchedulingDashboardSummary,
  SchedulingEventType,
  SchedulingEventTypeCreateRequest,
  SchedulingEventTypeUpdateRequest,
  SchedulingProviderCapabilities,
  SchedulingResource,
  SchedulingResourceCalendar,
  SchedulingSchedule,
  SchedulingScheduleCreateRequest,
  SchedulingScheduleUpdateRequest,
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

// Providers & Capabilities
export function fetchSchedulingProviders(accessToken: string) {
  return schedulingApi<SchedulingProviderCapabilities[]>('GET', 'providers', accessToken);
}

// Schedules
export function fetchSchedules(accessToken: string) {
  return schedulingApi<SchedulingSchedule[]>('GET', 'schedules', accessToken);
}

export function createSchedule(accessToken: string, payload: SchedulingScheduleCreateRequest) {
  return schedulingApi<SchedulingSchedule>('POST', 'schedules', accessToken, undefined, payload);
}

export function updateSchedule(accessToken: string, scheduleId: string, payload: SchedulingScheduleUpdateRequest) {
  return schedulingApi<SchedulingSchedule>('PATCH', `schedules/${scheduleId}`, accessToken, undefined, payload);
}

export function deleteSchedule(accessToken: string, scheduleId: string) {
  return schedulingApi<{ status: string }>('DELETE', `schedules/${scheduleId}`, accessToken);
}

// Event Types
export function fetchEventTypes(accessToken: string) {
  return schedulingApi<SchedulingEventType[]>('GET', 'event-types', accessToken);
}

export function createEventType(accessToken: string, payload: SchedulingEventTypeCreateRequest) {
  return schedulingApi<SchedulingEventType>('POST', 'event-types', accessToken, undefined, payload);
}

export function updateEventType(accessToken: string, eventTypeId: string, payload: SchedulingEventTypeUpdateRequest) {
  return schedulingApi<SchedulingEventType>('PATCH', `event-types/${eventTypeId}`, accessToken, undefined, payload);
}

export function deleteEventType(accessToken: string, eventTypeId: string) {
  return schedulingApi<{ status: string }>('DELETE', `event-types/${eventTypeId}`, accessToken);
}

// Cal.com Sync & Discovery
export function syncCalComProvider(accessToken: string) {
  return schedulingApi<CalComDiscoveryResponse>('POST', 'providers/calcom/sync', accessToken);
}

export function fetchCalComDiscovery(accessToken: string) {
  return schedulingApi<CalComDiscoveryResponse>('GET', 'providers/calcom/discovery', accessToken);
}
