import type { VoiceExperienceStatus } from '@/types/voice-experiences';

/**
 * Single fail-closed rule for offering physical deletion in the UI. Deletion is
 * only offered for an archived experience with a CONFIRMED empty history.
 * `versionCount === null` means the history could not be determined and must
 * never enable deletion. The backend remains the authority and rejects the rest.
 */
export function canDeleteArchivedExperience(
  status: VoiceExperienceStatus,
  versionCount: number | null,
): boolean {
  return status === 'archived' && versionCount === 0;
}
