'use client';

import { Mic, PhoneOff } from 'lucide-react';

import { usePublicVoiceRuntime } from '@/hooks/usePublicVoiceRuntime';
import type { PublicVoiceMessages } from './PublicVoiceExperience';

interface Props {
  slug: string;
  contextToken: string;
  callLabel: string;
  autoStart: boolean;
  showMicrophoneHelp: boolean;
  messages: PublicVoiceMessages;
}

export function PublicVoiceCall({ slug, contextToken, callLabel, autoStart, showMicrophoneHelp, messages }: Props) {
  const { state, error, start, hangup } = usePublicVoiceRuntime(slug, contextToken);
  const busy = ['requesting_permission', 'starting_call', 'connecting'].includes(state);

  return (
    <div className="mt-7 rounded-2xl border border-slate-200 bg-slate-50 p-5" data-testid="public-voice-call">
      {showMicrophoneHelp && state === 'idle' ? <p className="text-sm text-slate-600">{messages.microphoneHelp}</p> : null}
      {state === 'connected' ? (
        <button type="button" onClick={hangup} className="mt-4 min-h-12 w-full rounded-xl bg-rose-700 px-5 text-sm font-semibold text-white">
          <PhoneOff className="mr-2 inline size-4" aria-hidden="true" />{messages.endCall}
        </button>
      ) : state === 'ended' ? (
        <p className="mt-4 text-sm font-semibold text-slate-700" role="status">{messages.callEnded}</p>
      ) : (
        <button
          type="button"
          autoFocus={autoStart}
          disabled={busy}
          onClick={start}
          className="mt-4 min-h-12 w-full rounded-xl bg-[var(--voice-accent)] px-5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
        >
          <Mic className="mr-2 inline size-4" aria-hidden="true" />{busy ? messages.callLoading : callLabel}
        </button>
      )}
      {state === 'connected' ? <p className="mt-3 text-center text-sm font-semibold text-emerald-700" role="status">{messages.callConnected}</p> : null}
      {error ? <p className="mt-3 text-sm text-rose-700" role="alert">{messages.errors[error] || messages.errors.internal_error}</p> : null}
    </div>
  );
}
