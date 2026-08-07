import type { VoiceExperienceWriteRequest } from '@/types/voice-experiences';

export function isVoiceExperienceDirty(
  current: VoiceExperienceWriteRequest,
  initial: VoiceExperienceWriteRequest
) {
  return JSON.stringify(current) !== JSON.stringify(initial);
}

export function isVoiceExperienceAgentLocked(
  mode: 'create' | 'edit',
  versionsUnknown: boolean,
  versionCount: number
) {
  return mode === 'edit' && (versionsUnknown || versionCount > 0);
}
