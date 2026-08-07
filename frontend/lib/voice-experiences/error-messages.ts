const ERROR_KEYS = {
  'Maximum voice experiences limit reached.': 'maximumReached',
  'Could not allocate a unique experience slug.': 'slugConflict',
  'Voice experience is already published.': 'alreadyPublished',
  'Only an active context schema can be published.': 'activeSchemaRequired',
  'A concurrent publication already won.': 'concurrentPublication',
  'Only a published experience can be unpublished.': 'publishedRequired',
  'A published experience must be unpublished before archiving.': 'unpublishBeforeArchive',
  'Voice context schema does not belong to the selected voice agent.': 'schemaAgentMismatch',
  'Archived voice experiences are immutable.': 'archivedImmutable',
  'Only archived voice experiences can be deleted.': 'deleteRequiresArchived',
  'Voice experience agent cannot change after publication history exists.': 'agentChangeBlocked',
  'Voice experience with publication history cannot be deleted.': 'deleteHistoryBlocked',
} as const;

export function getVoiceExperienceErrorKey(detail: string) {
  return ERROR_KEYS[detail as keyof typeof ERROR_KEYS];
}

/**
 * Maps an HTTP status + backend detail to a SAFE i18n message key. A raw,
 * unknown backend detail is never returned to the user: unknown 409/422 fall
 * back to localized conflict/validation messages. The returned key is relative
 * to the `crm.voiceExperiences` translation namespace.
 */
export function getVoiceExperienceMessageKey(status: number, detail: string): string {
  const backendKey = getVoiceExperienceErrorKey(detail);
  if ((status === 409 || status === 422) && backendKey) return `errors.backend.${backendKey}`;
  if (status === 409) return 'errors.conflict';
  if (status === 422) return 'errors.validation';
  if (status === 403) return 'errors.accessDenied';
  if (status === 404) return 'errors.notFound';
  return 'errors.generic';
}
