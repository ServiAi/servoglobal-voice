import type {
  VoiceContextCollectionMode,
  VoiceContextFieldResponse,
} from '@/types/voice-experiences';

/**
 * Single source of truth for which collection modes appear in the pre-call
 * form. Fields collected during the call or kept internal never render in a
 * pre-call form. The future public runtime must reuse this exact policy.
 */
export const PRE_CALL_VISIBLE_MODES: readonly VoiceContextCollectionMode[] = [
  'ask_if_missing',
  'prefill_and_confirm',
  'trust_prefill',
];

export function isPreCallVisibleMode(mode: VoiceContextCollectionMode): boolean {
  return PRE_CALL_VISIBLE_MODES.includes(mode);
}

/**
 * Returns the context fields shown in the pre-call form, ordered by position.
 * `internal_only` and `collect_during_call` are always excluded.
 */
export function getPreCallVisibleContextFields<
  T extends Pick<VoiceContextFieldResponse, 'collection_mode' | 'position'>,
>(fields: readonly T[]): T[] {
  return fields
    .filter((field) => isPreCallVisibleMode(field.collection_mode))
    .sort((a, b) => a.position - b.position);
}
