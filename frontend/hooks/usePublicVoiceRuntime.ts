'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { launchPublicVoiceCall, type PublicCallErrorCode } from '@/lib/api/public-voice-calls';
import type { VoiceRuntimeAdapter } from '@/lib/voice-runtime/adapter';
import { FakeVoiceRuntimeAdapter } from '@/lib/voice-runtime/fake-adapter';
import { UltravoxVoiceRuntimeAdapter } from '@/lib/voice-runtime/ultravox-adapter';

export type PublicVoiceRuntimeState =
  | 'idle'
  | 'requesting_permission'
  | 'starting_call'
  | 'connecting'
  | 'connected'
  | 'ended'
  | 'error';

export function usePublicVoiceRuntime(slug: string, contextToken: string) {
  const [state, setState] = useState<PublicVoiceRuntimeState>('idle');
  const [error, setError] = useState<PublicCallErrorCode | 'microphone_unavailable' | null>(null);
  const busy = useRef(false);
  const adapter = useRef<VoiceRuntimeAdapter | null>(null);

  useEffect(() => () => adapter.current?.disconnect(), []);

  const start = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setError(null);
    setState('requesting_permission');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
    } catch {
      setError('microphone_unavailable');
      setState('error');
      busy.current = false;
      return;
    }
    setState('starting_call');
    const result = await launchPublicVoiceCall(slug, contextToken);
    if (!result.ok) {
      setError(result.error);
      setState('error');
      busy.current = false;
      return;
    }
    adapter.current = process.env.NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE === '1'
      ? new FakeVoiceRuntimeAdapter()
      : new UltravoxVoiceRuntimeAdapter();
    try {
      await adapter.current.connect(result.data.join_url, setState);
    } catch {
      adapter.current.disconnect();
      setError('call_provider_unavailable');
      setState('error');
      busy.current = false;
    }
  }, [contextToken, slug]);

  const hangup = useCallback(() => {
    adapter.current?.disconnect();
    setState('ended');
    busy.current = false;
  }, []);

  return { state, error, start, hangup };
}
