'use client';

import { PhoneCall } from 'lucide-react';
import { useState } from 'react';

import { requestPublicVoiceCallback } from '@/lib/api/public-voice-calls';
import type { PublicVoiceMessages } from './PublicVoiceExperience';


interface Props {
  slug: string;
  contextToken: string;
  callLabel: string;
  messages: PublicVoiceMessages;
}


export function PublicVoiceCallback({ slug, contextToken, callLabel, messages }: Props) {
  const [state, setState] = useState<'idle' | 'requesting' | 'accepted'>('idle');
  const [error, setError] = useState<string | null>(null);

  const requestCall = async () => {
    if (state !== 'idle') return;
    setState('requesting');
    setError(null);
    const result = await requestPublicVoiceCallback(slug, contextToken);
    if (!result.ok) {
      setState('idle');
      setError(result.error);
      return;
    }
    setState('accepted');
  };

  return (
    <div className="mt-7 rounded-2xl border border-slate-200 bg-slate-50 p-5">
      {state === 'accepted' ? (
        <p className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-800" role="status">
          {messages.callbackAccepted}
        </p>
      ) : (
        <button
          type="button"
          disabled={state === 'requesting'}
          onClick={requestCall}
          className="min-h-12 w-full rounded-xl bg-[var(--voice-accent)] px-5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-60"
        >
          <PhoneCall className="mr-2 inline size-4" aria-hidden="true" />
          {state === 'requesting' ? messages.callbackLoading : callLabel}
        </button>
      )}
      {error ? (
        <p className="mt-3 text-sm text-rose-700" role="alert">
          {messages.errors[error] || messages.errors.internal_error}
        </p>
      ) : null}
    </div>
  );
}
