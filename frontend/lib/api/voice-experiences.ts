import 'server-only';

import { requestVoiceEndpoint } from './crm';
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

export function fetchVoiceExperiences(accessToken: string) {
  return requestVoiceEndpoint<VoiceExperienceResponse[]>('GET', 'experiences', accessToken);
}

export function fetchVoiceExperience(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<VoiceExperienceResponse>('GET', `experiences/${experienceId}`, accessToken);
}

export function createVoiceExperience(accessToken: string, payload: VoiceExperienceWriteRequest) {
  return requestVoiceEndpoint<VoiceExperienceResponse>('POST', 'experiences', accessToken, undefined, payload);
}

export function updateVoiceExperience(
  accessToken: string,
  experienceId: string,
  payload: VoiceExperienceWriteRequest
) {
  return requestVoiceEndpoint<VoiceExperienceResponse>(
    'PUT',
    `experiences/${experienceId}`,
    accessToken,
    undefined,
    payload
  );
}

export function publishVoiceExperience(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<VoiceExperienceResponse>('POST', `experiences/${experienceId}/publish`, accessToken);
}

export function unpublishVoiceExperience(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<VoiceExperienceResponse>('POST', `experiences/${experienceId}/unpublish`, accessToken);
}

export function archiveVoiceExperience(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<VoiceExperienceResponse>('POST', `experiences/${experienceId}/archive`, accessToken);
}

export function deleteVoiceExperience(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<null>('DELETE', `experiences/${experienceId}`, accessToken);
}

export function fetchVoiceExperienceVersions(accessToken: string, experienceId: string) {
  return requestVoiceEndpoint<VoiceExperienceVersionResponse[]>(
    'GET',
    `experiences/${experienceId}/versions`,
    accessToken
  );
}

export function fetchVoiceContextSchemas(accessToken: string, agentConfigId: string) {
  return requestVoiceEndpoint<VoiceContextSchemaSummaryResponse[]>(
    'GET',
    `agents/${agentConfigId}/context-schemas`,
    accessToken
  );
}

export function createVoiceContextSchema(
  accessToken: string,
  agentConfigId: string,
  payload: VoiceContextSchemaCreateRequest
) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>(
    'POST',
    `agents/${agentConfigId}/context-schemas`,
    accessToken,
    undefined,
    payload
  );
}

export function fetchVoiceContextSchemaVersions(
  accessToken: string,
  agentConfigId: string,
  schemaKey: string
) {
  return requestVoiceEndpoint<VoiceContextSchemaSummaryResponse[]>(
    'GET',
    `agents/${agentConfigId}/context-schemas/${schemaKey}/versions`,
    accessToken
  );
}

export function fetchVoiceContextSchema(accessToken: string, schemaId: string) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>('GET', `context-schemas/${schemaId}`, accessToken);
}

export function updateVoiceContextSchemaMeta(
  accessToken: string,
  schemaId: string,
  payload: VoiceContextSchemaMetaUpdateRequest
) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>(
    'PUT',
    `context-schemas/${schemaId}`,
    accessToken,
    undefined,
    payload
  );
}

export function addVoiceContextField(
  accessToken: string,
  schemaId: string,
  payload: VoiceContextFieldRequest
) {
  return requestVoiceEndpoint<VoiceContextFieldResponse>(
    'POST',
    `context-schemas/${schemaId}/fields`,
    accessToken,
    undefined,
    payload
  );
}

export function updateVoiceContextField(
  accessToken: string,
  schemaId: string,
  fieldId: string,
  payload: VoiceContextFieldRequest
) {
  return requestVoiceEndpoint<VoiceContextFieldResponse>(
    'PUT',
    `context-schemas/${schemaId}/fields/${fieldId}`,
    accessToken,
    undefined,
    payload
  );
}

export function deleteVoiceContextField(
  accessToken: string,
  schemaId: string,
  fieldId: string
) {
  return requestVoiceEndpoint<null>(
    'DELETE',
    `context-schemas/${schemaId}/fields/${fieldId}`,
    accessToken
  );
}

export function activateVoiceContextSchema(accessToken: string, schemaId: string) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>(
    'POST',
    `context-schemas/${schemaId}/activate`,
    accessToken
  );
}

export function archiveVoiceContextSchema(accessToken: string, schemaId: string) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>(
    'POST',
    `context-schemas/${schemaId}/archive`,
    accessToken
  );
}

export function forkVoiceContextSchemaVersion(accessToken: string, schemaId: string) {
  return requestVoiceEndpoint<VoiceContextSchemaResponse>(
    'POST',
    `context-schemas/${schemaId}/new-version`,
    accessToken
  );
}
