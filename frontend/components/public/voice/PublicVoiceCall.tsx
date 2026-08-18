'use client';

import { Mic, PhoneOff } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

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

function formatDuration(totalSeconds: number) {
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const clock = [minutes, seconds].map((value) => String(value).padStart(2, '0')).join(':');
  return hours ? `${String(hours).padStart(2, '0')}:${clock}` : clock;
}

function VoiceActivityOrb({ active, stream, label }: { active: boolean; stream: MediaStream | null; label: string }) {
  const orbRef = useRef<HTMLDivElement>(null);
  const glowRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const orb = orbRef.current;
    const glow = glowRef.current;
    if (!orb || !glow || !active || !stream) return;

    let frame = 0;
    let context: AudioContext | null = null;
    let source: MediaStreamAudioSourceNode | null = null;
    try {
      context = new AudioContext();
      const analyser = context.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.82;
      source = context.createMediaStreamSource(stream);
      source.connect(analyser);
      const spectrum = new Uint8Array(analyser.frequencyBinCount);
      const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      let smoothedLevel = 0;

      const draw = () => {
        analyser.getByteFrequencyData(spectrum);
        const average = spectrum.reduce((sum, value) => sum + value, 0) / spectrum.length / 255;
        const level = Math.min(1, Math.max(0, (average - 0.025) * 4.8));
        smoothedLevel = smoothedLevel * 0.78 + level * 0.22;
        const hue = Math.round(190 + smoothedLevel * 125);
        orb.style.transform = `scale(${reducedMotion ? 1 : 1 + smoothedLevel * 0.2})`;
        orb.style.background = `radial-gradient(circle at 32% 27%, hsl(${hue} 100% 96%) 0%, hsl(${hue} 92% 68%) 22%, hsl(${hue + 24} 82% 48%) 58%, hsl(222 48% 16%) 100%)`;
        glow.style.background = `hsl(${hue} 88% 58%)`;
        glow.style.opacity = String(0.22 + smoothedLevel * 0.58);
        frame = requestAnimationFrame(draw);
      };

      void context.resume();
      draw();
    } catch {
      orb.style.transform = 'scale(1)';
    }

    return () => {
      cancelAnimationFrame(frame);
      source?.disconnect();
      void context?.close();
      orb.style.transform = 'scale(1)';
      glow.style.opacity = '0.2';
    };
  }, [active, stream]);

  return (
    <div className="relative mx-auto flex size-40 items-center justify-center" data-testid="voice-activity-orb" role="img" aria-label={label}>
      <div ref={glowRef} className="absolute inset-5 rounded-full bg-cyan-400 opacity-20 blur-2xl transition-opacity duration-100 motion-reduce:transition-none" />
      <div className="absolute inset-3 rounded-full border border-[var(--voice-accent)]/20" />
      <div className="absolute inset-7 rounded-full border border-white/70 shadow-[inset_0_0_24px_rgba(255,255,255,0.45)]" />
      <div
        ref={orbRef}
        className="relative size-24 rounded-full border border-white/70 shadow-[0_18px_45px_rgba(8,145,178,0.28),inset_-12px_-16px_28px_rgba(15,23,42,0.32),inset_10px_10px_24px_rgba(255,255,255,0.38)] transition-transform duration-75 will-change-transform motion-reduce:transition-none"
        style={{ background: 'radial-gradient(circle at 32% 27%, #ecfeff 0%, #67e8f9 22%, #0891b2 58%, #172554 100%)' }}
      >
        <span className="absolute left-[22%] top-[17%] size-6 rounded-full bg-white/45 blur-sm" aria-hidden="true" />
      </div>
    </div>
  );
}

export function PublicVoiceCall({ slug, contextToken, callLabel, autoStart, showMicrophoneHelp, messages }: Props) {
  const { state, error, microphoneStream, start, hangup } = usePublicVoiceRuntime(slug, contextToken);
  const [duration, setDuration] = useState(0);
  const busy = ['requesting_permission', 'starting_call', 'connecting'].includes(state);
  const connected = state === 'connected';
  const showSession = busy || connected || state === 'ended';

  useEffect(() => {
    if (!connected) return;
    const startedAt = Date.now();
    setDuration(0);
    const timer = window.setInterval(() => {
      setDuration(Math.floor((Date.now() - startedAt) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [connected]);

  return (
    <div className="mt-7 overflow-hidden rounded-2xl border border-slate-200 bg-[radial-gradient(circle_at_top,_rgba(34,211,238,0.09),_transparent_48%),linear-gradient(180deg,#f8fafc,#f1f5f9)] p-5" data-testid="public-voice-call">
      {showMicrophoneHelp && state === 'idle' ? <p className="text-sm text-slate-600">{messages.microphoneHelp}</p> : null}
      {showSession ? (
        <div className="py-2 text-center">
          <VoiceActivityOrb active={connected} stream={microphoneStream} label={messages.voiceActivity} />
          {(connected || state === 'ended') ? (
            <div className="mx-auto mt-1 inline-flex items-center gap-2 rounded-full border border-slate-200/80 bg-white/80 px-3 py-1.5 shadow-sm backdrop-blur">
              <span className={`size-2 rounded-full ${connected ? 'animate-pulse bg-emerald-500' : 'bg-slate-400'}`} aria-hidden="true" />
              <span className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{messages.callDuration}</span>
              <time className="font-mono text-sm font-bold tabular-nums text-slate-900" data-testid="call-duration">{formatDuration(duration)}</time>
            </div>
          ) : null}
        </div>
      ) : null}
      {connected ? (
        <button type="button" onClick={hangup} className="mt-4 min-h-12 w-full rounded-xl bg-rose-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-rose-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-600 focus-visible:ring-offset-2">
          <PhoneOff className="mr-2 inline size-4" aria-hidden="true" />{messages.endCall}
        </button>
      ) : state === 'ended' ? (
        <p className="mt-4 text-center text-sm font-semibold text-slate-700" role="status">{messages.callEnded}</p>
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
