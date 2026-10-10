'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { launchPublicVoiceCall, type PublicCallErrorCode } from '@/lib/api/public-voice-calls';
import type { VoiceRuntimeAdapter } from '@/lib/voice-runtime/adapter';
import { FakeVoiceRuntimeAdapter } from '@/lib/voice-runtime/fake-adapter';

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

  useEffect(() => () => {
    void adapter.current?.disconnect();
  }, []);

  const start = useCallback(async () => {
    if (busy.current) return;
    busy.current = true;
    setError(null);
    setState('requesting_permission');
    try {
      // Permission prompt only. The probe is released at once: LiveKit captures and
      // publishes the one real microphone track after the call has been authorized.
      const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
      probe.getTracks().forEach((track) => track.stop());
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
    const join = { serverUrl: result.data.server_url, participantToken: result.data.participant_token };
    try {
      if (process.env.NEXT_PUBLIC_VOICE_PUBLIC_WEBRTC_TEST_MODE === '1') {
        adapter.current = new FakeVoiceRuntimeAdapter();
      } else {
        const { LiveKitVoiceRuntimeAdapter } = await import('@/lib/voice-runtime/livekit-adapter');
        adapter.current = new LiveKitVoiceRuntimeAdapter({ onMicrophoneStream: setMicrophoneStream });
      }
      await adapter.current.connect(join, (nextState) => {
        setState(nextState);
        if (nextState === 'ended' || nextState === 'error') {
          setMicrophoneStream(null);
          busy.current = false;
        }
      });
    } catch {
      void adapter.current?.disconnect();
      setMicrophoneStream(null);
      setError('call_provider_unavailable');
      setState('error');
      busy.current = false;
    }
  }, [contextToken, slug]);

  const hangup = useCallback(() => {
    void adapter.current?.disconnect();
    setMicrophoneStream(null);
    setState('ended');
    busy.current = false;
  }, []);

  return { state, error, microphoneStream, start, hangup };
}
