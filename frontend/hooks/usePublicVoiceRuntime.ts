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
  const [microphoneStream, setMicrophoneStream] = useState<MediaStream | null>(null);
  const busy = useRef(false);
  const adapter = useRef<VoiceRuntimeAdapter | null>(null);
  const microphoneStreamRef = useRef<MediaStream | null>(null);

  const releaseMicrophone = useCallback(() => {
    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
    microphoneStreamRef.current = null;
    setMicrophoneStream(null);
  }, []);

  useEffect(() => () => {
    adapter.current?.disconnect();
    microphoneStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

  const start = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setError(null);
    setState('requesting_permission');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      microphoneStreamRef.current = stream;
      setMicrophoneStream(stream);
    } catch {
      setError('microphone_unavailable');
      setState('error');
      busy.current = false;
      return;
    }
    setState('starting_call');
    const result = await launchPublicVoiceCall(slug, contextToken);
    if (!result.ok) {
      releaseMicrophone();
      setError(result.error);
      setState('error');
      busy.current = false;
      return;
    }
    adapter.current = process.env.NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE === '1'
      ? new FakeVoiceRuntimeAdapter()
      : new UltravoxVoiceRuntimeAdapter();
    try {
      await adapter.current.connect(result.data.join_url, (nextState) => {
        setState(nextState);
        if (nextState === 'ended' || nextState === 'error') {
          releaseMicrophone();
          busy.current = false;
        }
      });
    } catch {
      adapter.current.disconnect();
      releaseMicrophone();
      setError('call_provider_unavailable');
      setState('error');
      busy.current = false;
    }
  }, [contextToken, releaseMicrophone, slug]);

  const hangup = useCallback(() => {
    adapter.current?.disconnect();
    releaseMicrophone();
    setState('ended');
    busy.current = false;
  }, [releaseMicrophone]);

  return { state, error, microphoneStream, start, hangup };
}
