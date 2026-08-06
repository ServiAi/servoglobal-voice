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
} as const;

export function getVoiceExperienceErrorKey(detail: string) {
  return ERROR_KEYS[detail as keyof typeof ERROR_KEYS];
}
