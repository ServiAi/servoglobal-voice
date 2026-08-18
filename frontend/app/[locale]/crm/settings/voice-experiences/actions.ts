'use server';

import { revalidatePath } from 'next/cache';
import type { FetchResult } from '@/lib/api/crm';
import {
  activateVoiceContextSchema,
  addVoiceContextField,
  archiveVoiceContextSchema,
  archiveVoiceExperience,
  createVoiceContextSchema,
  createVoiceExperience,
  deleteVoiceContextField,
  deleteVoiceContextSchema,
  deleteVoiceExperience,
  deleteVoiceExperienceVersion,
  fetchVoiceContextSchema,
  fetchVoiceContextSchemas,
  fetchVoiceContextSchemaVersions,
  fetchVoiceExperienceVersions,
  forkVoiceContextSchemaVersion,
  publishVoiceExperience,
  unpublishVoiceExperience,
  updateVoiceContextField,
  updateVoiceContextSchemaMeta,
  updateVoiceExperience,
} from '@/lib/api/voice-experiences';
import { getAccessToken } from '@/lib/auth/server';
import type {
  VoiceContextFieldRequest,
  VoiceContextFieldResponse,
  VoiceContextSchemaCreateRequest,
  VoiceContextSchemaMetaUpdateRequest,
  VoiceContextSchemaResponse,
  VoiceContextSchemaSummaryResponse,
  VoiceExperienceResponse,
  VoiceExperienceVersionResponse,
  VoiceExperienceWriteRequest,
} from '@/types/voice-experiences';

async function withAccessToken<T>(
  run: (accessToken: string) => Promise<FetchResult<T>>
): Promise<FetchResult<T>> {
  const accessToken = await getAccessToken();
  if (!accessToken) return { ok: false, status: 401, detail: 'unauthorized' };
  return run(accessToken);
}

function revalidateVoiceExperiences(locale: string) {
  revalidatePath(`/${locale}/crm/settings/voice-experiences`, 'layout');
}

export async function createVoiceExperienceAction(
  locale: string,
  payload: VoiceExperienceWriteRequest
): Promise<FetchResult<VoiceExperienceResponse>> {
  const result = await withAccessToken((token) => createVoiceExperience(token, payload));
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function updateVoiceExperienceAction(
  locale: string,
  experienceId: string,
  payload: VoiceExperienceWriteRequest
): Promise<FetchResult<VoiceExperienceResponse>> {
  const result = await withAccessToken((token) =>
    updateVoiceExperience(token, experienceId, payload)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function publishVoiceExperienceAction(
  locale: string,
  experienceId: string
): Promise<FetchResult<VoiceExperienceResponse>> {
  const result = await withAccessToken((token) =>
    publishVoiceExperience(token, experienceId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function unpublishVoiceExperienceAction(
  locale: string,
  experienceId: string
): Promise<FetchResult<VoiceExperienceResponse>> {
  const result = await withAccessToken((token) =>
    unpublishVoiceExperience(token, experienceId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function archiveVoiceExperienceAction(
  locale: string,
  experienceId: string
): Promise<FetchResult<VoiceExperienceResponse>> {
  const result = await withAccessToken((token) =>
    archiveVoiceExperience(token, experienceId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function deleteVoiceExperienceAction(
  locale: string,
  experienceId: string
): Promise<FetchResult<null>> {
  const result = await withAccessToken((token) =>
    deleteVoiceExperience(token, experienceId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function fetchVoiceExperienceVersionsAction(
  experienceId: string
): Promise<FetchResult<VoiceExperienceVersionResponse[]>> {
  return withAccessToken((token) => fetchVoiceExperienceVersions(token, experienceId));
}

export async function deleteVoiceExperienceVersionAction(
  locale: string,
  experienceId: string,
  versionId: string
): Promise<FetchResult<null>> {
  const result = await withAccessToken((token) =>
    deleteVoiceExperienceVersion(token, experienceId, versionId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function fetchVoiceContextSchemasAction(
  agentConfigId: string
): Promise<FetchResult<VoiceContextSchemaSummaryResponse[]>> {
  return withAccessToken((token) => fetchVoiceContextSchemas(token, agentConfigId));
}

export async function fetchVoiceContextSchemaAction(
  schemaId: string
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  return withAccessToken((token) => fetchVoiceContextSchema(token, schemaId));
}

export async function fetchVoiceContextSchemaVersionsAction(
  agentConfigId: string,
  schemaKey: string
): Promise<FetchResult<VoiceContextSchemaSummaryResponse[]>> {
  return withAccessToken((token) =>
    fetchVoiceContextSchemaVersions(token, agentConfigId, schemaKey)
  );
}

export async function createVoiceContextSchemaAction(
  locale: string,
  agentConfigId: string,
  payload: VoiceContextSchemaCreateRequest
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  const result = await withAccessToken((token) =>
    createVoiceContextSchema(token, agentConfigId, payload)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function updateVoiceContextSchemaMetaAction(
  locale: string,
  schemaId: string,
  payload: VoiceContextSchemaMetaUpdateRequest
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  const result = await withAccessToken((token) =>
    updateVoiceContextSchemaMeta(token, schemaId, payload)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function addVoiceContextFieldAction(
  locale: string,
  schemaId: string,
  payload: VoiceContextFieldRequest
): Promise<FetchResult<VoiceContextFieldResponse>> {
  const result = await withAccessToken((token) =>
    addVoiceContextField(token, schemaId, payload)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function updateVoiceContextFieldAction(
  locale: string,
  schemaId: string,
  fieldId: string,
  payload: VoiceContextFieldRequest
): Promise<FetchResult<VoiceContextFieldResponse>> {
  const result = await withAccessToken((token) =>
    updateVoiceContextField(token, schemaId, fieldId, payload)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function deleteVoiceContextFieldAction(
  locale: string,
  schemaId: string,
  fieldId: string
): Promise<FetchResult<null>> {
  const result = await withAccessToken((token) =>
    deleteVoiceContextField(token, schemaId, fieldId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function activateVoiceContextSchemaAction(
  locale: string,
  schemaId: string
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  const result = await withAccessToken((token) =>
    activateVoiceContextSchema(token, schemaId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function archiveVoiceContextSchemaAction(
  locale: string,
  schemaId: string
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  const result = await withAccessToken((token) =>
    archiveVoiceContextSchema(token, schemaId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function deleteVoiceContextSchemaAction(
  locale: string,
  schemaId: string
): Promise<FetchResult<null>> {
  const result = await withAccessToken((token) =>
    deleteVoiceContextSchema(token, schemaId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}

export async function forkVoiceContextSchemaVersionAction(
  locale: string,
  schemaId: string
): Promise<FetchResult<VoiceContextSchemaResponse>> {
  const result = await withAccessToken((token) =>
    forkVoiceContextSchemaVersion(token, schemaId)
  );
  if (result.ok) revalidateVoiceExperiences(locale);
  return result;
}
