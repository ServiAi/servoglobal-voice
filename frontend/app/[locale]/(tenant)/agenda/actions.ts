'use server';

import { getAccessToken } from '@/lib/auth/server';
import type { FetchResult } from '@/lib/api/crm';
import {
  addSchedulingTeamMember,
  assignCalendarToResource,
  createSchedulingException,
  createSchedulingResource,
  createSchedulingTeam,
  deleteSchedulingException,
  deleteSchedulingResource,
  deleteSchedulingTeam,
  removeSchedulingTeamMember,
  updateResourceAvailability,
  updateSchedulingConfig,
  updateSchedulingResource,
  updateSchedulingTeam,
  upsertAgentSchedulingConfig,
} from '@/lib/api/scheduling';
import type {
  AgentSchedulingConfig,
  SchedulingAvailabilityException,
  SchedulingResource,
  SchedulingResourceCalendar,
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
