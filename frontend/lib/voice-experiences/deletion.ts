import type { VoiceExperienceStatus } from '@/types/voice-experiences';

export function canDeleteArchivedExperience(
  status: VoiceExperienceStatus,
): boolean {
  return status === 'archived';
}
