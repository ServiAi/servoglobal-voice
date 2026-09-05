'use server';

import { getAccessToken } from '@/lib/auth/server';
import type { FetchResult } from '@/lib/api/crm';
import {
  addSchedulingTeamMember,
  assignCalendarToResource,
  createEventType,
  createSchedule,
  createSchedulingException,
  createSchedulingResource,
  createSchedulingTeam,
  deleteEventType,
  deleteSchedule,
  deleteSchedulingException,
  deleteSchedulingResource,
  deleteSchedulingTeam,
  fetchCalComDiscovery,
  fetchEventTypes,
  fetchSchedules,
  fetchSchedulingProviders,
  removeSchedulingTeamMember,
  syncCalComProvider,
  updateEventType,
  updateResourceAvailability,
  updateSchedule,
  updateSchedulingConfig,
  updateSchedulingResource,
  updateSchedulingTeam,
  upsertAgentSchedulingConfig,
} from '@/lib/api/scheduling';
import type {
  AgentSchedulingConfig,
  CalComDiscoveryResponse,
  SchedulingAvailabilityException,
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


async function withAccessToken<T>(run: (accessToken: string) => Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    return { ok: false, status: 401, detail: 'unauthorized' };
  }
  return run(accessToken);
}

export async function updateSchedulingConfigAction(
  payload: Partial<TenantSchedulingConfig>
): Promise<FetchResult<TenantSchedulingConfig>> {
  return withAccessToken((accessToken) => updateSchedulingConfig(accessToken, payload));
}

export async function createSchedulingResourceAction(
  payload: Partial<SchedulingResource>
): Promise<FetchResult<SchedulingResource>> {
  return withAccessToken((accessToken) => createSchedulingResource(accessToken, payload));
}

export async function updateSchedulingResourceAction(
  resourceId: string,
  payload: Partial<SchedulingResource>
): Promise<FetchResult<SchedulingResource>> {
  return withAccessToken((accessToken) => updateSchedulingResource(accessToken, resourceId, payload));
}

export async function deleteSchedulingResourceAction(
  resourceId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => deleteSchedulingResource(accessToken, resourceId));
}

export async function updateResourceAvailabilityAction(
  resourceId: string,
  workingHours: Record<string, unknown>
): Promise<FetchResult<SchedulingResource>> {
  return withAccessToken((accessToken) => updateResourceAvailability(accessToken, resourceId, workingHours));
}

export async function assignCalendarToResourceAction(
  resourceId: string,
  payload: { calendar_id: string; is_blocking: boolean; is_destination: boolean }
): Promise<FetchResult<SchedulingResourceCalendar>> {
  return withAccessToken((accessToken) => assignCalendarToResource(accessToken, resourceId, payload));
}

export async function createSchedulingTeamAction(
  payload: Partial<SchedulingTeam>
): Promise<FetchResult<SchedulingTeam>> {
  return withAccessToken((accessToken) => createSchedulingTeam(accessToken, payload));
}

export async function updateSchedulingTeamAction(
  teamId: string,
  payload: Partial<SchedulingTeam>
): Promise<FetchResult<SchedulingTeam>> {
  return withAccessToken((accessToken) => updateSchedulingTeam(accessToken, teamId, payload));
}

export async function deleteSchedulingTeamAction(
  teamId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => deleteSchedulingTeam(accessToken, teamId));
}

export async function addSchedulingTeamMemberAction(
  teamId: string,
  payload: { resource_id: string; priority?: number; is_active?: boolean }
): Promise<FetchResult<SchedulingTeamMember>> {
  return withAccessToken((accessToken) => addSchedulingTeamMember(accessToken, teamId, payload));
}

export async function removeSchedulingTeamMemberAction(
  teamId: string,
  resourceId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => removeSchedulingTeamMember(accessToken, teamId, resourceId));
}

export async function createSchedulingExceptionAction(
  payload: Partial<SchedulingAvailabilityException>
): Promise<FetchResult<SchedulingAvailabilityException>> {
  return withAccessToken((accessToken) => createSchedulingException(accessToken, payload));
}

export async function deleteSchedulingExceptionAction(
  exceptionId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => deleteSchedulingException(accessToken, exceptionId));
}

export async function upsertAgentSchedulingConfigAction(
  agentId: string,
  payload: Partial<AgentSchedulingConfig>
): Promise<FetchResult<AgentSchedulingConfig>> {
  return withAccessToken((accessToken) => upsertAgentSchedulingConfig(accessToken, agentId, payload));
}

// Providers & Capabilities
export async function fetchSchedulingProvidersAction(): Promise<FetchResult<SchedulingProviderCapabilities[]>> {
  return withAccessToken((accessToken) => fetchSchedulingProviders(accessToken));
}

// Schedules
export async function fetchSchedulesAction(): Promise<FetchResult<SchedulingSchedule[]>> {
  return withAccessToken((accessToken) => fetchSchedules(accessToken));
}

export async function createScheduleAction(
  payload: SchedulingScheduleCreateRequest
): Promise<FetchResult<SchedulingSchedule>> {
  return withAccessToken((accessToken) => createSchedule(accessToken, payload));
}

export async function updateScheduleAction(
  scheduleId: string,
  payload: SchedulingScheduleUpdateRequest
): Promise<FetchResult<SchedulingSchedule>> {
  return withAccessToken((accessToken) => updateSchedule(accessToken, scheduleId, payload));
}

export async function deleteScheduleAction(
  scheduleId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => deleteSchedule(accessToken, scheduleId));
}

// Event Types
export async function fetchEventTypesAction(): Promise<FetchResult<SchedulingEventType[]>> {
  return withAccessToken((accessToken) => fetchEventTypes(accessToken));
}

export async function createEventTypeAction(
  payload: SchedulingEventTypeCreateRequest
): Promise<FetchResult<SchedulingEventType>> {
  return withAccessToken((accessToken) => createEventType(accessToken, payload));
}

export async function updateEventTypeAction(
  eventTypeId: string,
  payload: SchedulingEventTypeUpdateRequest
): Promise<FetchResult<SchedulingEventType>> {
  return withAccessToken((accessToken) => updateEventType(accessToken, eventTypeId, payload));
}

export async function deleteEventTypeAction(
  eventTypeId: string
): Promise<FetchResult<{ status: string }>> {
  return withAccessToken((accessToken) => deleteEventType(accessToken, eventTypeId));
}

// Cal.com Sync & Discovery
export async function syncCalComProviderAction(): Promise<FetchResult<CalComDiscoveryResponse>> {
  return withAccessToken((accessToken) => syncCalComProvider(accessToken));
}

export async function fetchCalComDiscoveryAction(): Promise<FetchResult<CalComDiscoveryResponse>> {
  return withAccessToken((accessToken) => fetchCalComDiscovery(accessToken));
}
