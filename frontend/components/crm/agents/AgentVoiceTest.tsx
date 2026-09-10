'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Headphones, Mic, MicOff, PhoneOff, Radio } from 'lucide-react';
import { useTranslations } from 'next-intl';

import {
  createVoiceTestSessionAction,
  createVoiceTestTokenAction,
} from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { LiveKitVoiceRuntimeAdapter } from '@/lib/voice-runtime/livekit-adapter';

type Stage =
  | 'idle'
  | 'preparing'
  | 'agentStarting'
  | 'waitingMicrophone'
  | 'connecting'
  | 'listening'
  | 'speaking'
  | 'ended'
  | 'error';

export function AgentVoiceTest({ agentId, agentName }: { agentId: string; agentName: string }) {
  const t = useTranslations('crm.agentBuilder.testCall');
  const adapter = useRef<LiveKitVoiceRuntimeAdapter | null>(null);
  const [open, setOpen] = useState(false);
  const [stage, setStage] = useState<Stage>('idle');
  const [microphoneActive, setMicrophoneActive] = useState(false);
  const [connected, setConnected] = useState(false);
  const [audioBlocked, setAudioBlocked] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const hangup = useCallback(() => {
    adapter.current?.disconnect();
    adapter.current = null;
    setMicrophoneActive(false);
    setConnected(false);
    setStage('ended');
  }, []);

  useEffect(
    () => () => {
      void adapter.current?.disconnect();
    },
    []
  );

  const start = useCallback(async () => {
    setOpen(true);
    setStage('preparing');
    setError(null);
    setAudioBlocked(false);
    const session = await createVoiceTestSessionAction(agentId, crypto.randomUUID());
    if (!session.ok || session.data.status === 'failed') {
      setError(session.ok ? t('errors.runtime') : session.detail);
      setStage('error');
      return;
    }

    setStage('agentStarting');
    const token = await createVoiceTestTokenAction(session.data.id);
    if (!token.ok) {
      setError(token.detail);
      setStage('error');
      return;
    }

    setStage('waitingMicrophone');
    const { LiveKitVoiceRuntimeAdapter } = await import('@/lib/voice-runtime/livekit-adapter');
    const runtime = new LiveKitVoiceRuntimeAdapter({
      onMicrophoneChange: setMicrophoneActive,
      onAgentSpeakingChange: (speaking) => setStage(speaking ? 'speaking' : 'listening'),
      onAudioPlaybackBlocked: () => setAudioBlocked(true),
    });
    adapter.current = runtime;
    setStage('connecting');
    try {
      await runtime.connect(
        {
          serverUrl: token.data.server_url,
          participantToken: token.data.participant_token,
        },
        (state) => {
          setConnected(state === 'connected');
          if (state === 'connected') setStage('listening');
          else if (state === 'ended') setStage('ended');
          else if (state === 'error') setStage('error');
        }
      );
    } catch {
      setError(t('errors.connection'));
      setStage('error');
    }
  }, [agentId, t]);

  return (
    <>
      <Button type="button" size="sm" onClick={start}>
        <Headphones className="mr-1.5 size-4" aria-hidden="true" />
        {t('cta')}
      </Button>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) hangup();
          setOpen(next);
        }}
      >
        <DialogContent className="grid max-h-[85dvh] grid-rows-[auto_minmax(0,1fr)_auto] gap-0 overflow-hidden p-0 sm:max-w-xl">
          <DialogHeader className="border-b border-border px-6 py-5">
            <DialogTitle>{t('title', { name: agentName })}</DialogTitle>
            <DialogDescription>{t('description')}</DialogDescription>
          </DialogHeader>
          <div className="min-h-0 space-y-5 overflow-y-auto px-6 py-6">
            <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/5 p-6 text-center">
              <span className="mx-auto flex size-16 items-center justify-center rounded-full bg-cyan-500/10 text-cyan-600">
                <Radio className={`size-7 ${stage === 'listening' || stage === 'speaking' ? 'animate-pulse' : ''}`} aria-hidden="true" />
              </span>
              <p className="mt-4 text-xs font-semibold uppercase tracking-[0.2em] text-muted-foreground">
                {t('statusLabel')}
              </p>
              <p className="mt-1 text-lg font-semibold text-foreground" aria-live="polite">
                {t(`states.${stage}`)}
              </p>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <StatusItem
                icon={microphoneActive ? Mic : MicOff}
                label={t('microphone')}
                value={t(microphoneActive ? 'active' : 'inactive')}
                active={microphoneActive}
              />
              <StatusItem
                icon={Radio}
                label={t('connection')}
                value={t(connected ? 'connected' : 'disconnected')}
                active={connected}
              />
            </div>
            {audioBlocked ? (
              <Button
                type="button"
                variant="outline"
                className="w-full"
                onClick={async () => {
                  await adapter.current?.enableAudio();
                  setAudioBlocked(false);
                }}
              >
                {t('enableAudio')}
              </Button>
            ) : null}
            {error ? (
              <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/5 p-3 text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>
          <DialogFooter className="border-t border-border px-6 py-4">
            <Button type="button" variant="destructive" onClick={hangup} disabled={stage === 'ended'}>
              <PhoneOff className="mr-2 size-4" aria-hidden="true" />
              {t('hangup')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function StatusItem({
  icon: Icon,
  label,
  value,
  active,
}: {
  icon: typeof Mic;
  label: string;
  value: string;
  active: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-muted/30 p-4">
      <Icon className={`size-5 ${active ? 'text-cyan-600' : 'text-muted-foreground'}`} aria-hidden="true" />
      <div>
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className="text-sm font-medium text-foreground">{value}</p>
      </div>
    </div>
  );
}
