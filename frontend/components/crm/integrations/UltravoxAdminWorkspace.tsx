'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { AlertTriangle, Bot, Link2, Loader2, Play, Radio, Volume2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { VoiceIntegrationCard } from './VoiceIntegrationCard';
import {
  fetchUltravoxAgents,
  fetchUltravoxVoices,
  importUltravoxAgent,
  ultravoxVoicePreviewUrl,
} from '@/lib/api/ultravox-admin';
import type { VoiceAgentConfigResponse, VoiceProviderConfigResponse } from '@/types/crm';
import type { UltravoxAgentPage, UltravoxVoicePage } from '@/types/ultravox-admin';

type Tab = 'connection' | 'agents' | 'voices' | 'status';
type Props = {
  accessToken: string;
  locale: string;
  initialConfig?: VoiceProviderConfigResponse;
  initialVoiceAgents: VoiceAgentConfigResponse[];
  initialAgents?: UltravoxAgentPage;
  initialVoices?: UltravoxVoicePage;
};

const tabs: Tab[] = ['connection', 'agents', 'voices', 'status'];

export function UltravoxAdminWorkspace({
  accessToken,
  locale,
  initialConfig,
  initialVoiceAgents,
  initialAgents,
  initialVoices,
}: Props) {
  const t = useTranslations('crm.ultravoxAdmin');
  const router = useRouter();
  const [tab, setTab] = useState<Tab>('connection');
  const [agents, setAgents] = useState(initialAgents);
  const [voices, setVoices] = useState(initialVoices);
  const [search, setSearch] = useState('');
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const active = initialConfig?.status === 'active';
  const blockingTools = useMemo(
    () => agents?.results.filter((agent) => agent.has_unsupported_client_tools).length ?? 0,
    [agents]
  );

  async function reload(kind: 'agents' | 'voices') {
    setBusy(kind);
    setMessage(null);
    const result = kind === 'agents'
      ? await fetchUltravoxAgents(accessToken, { search: search || undefined, pageSize: 50 })
      : await fetchUltravoxVoices(accessToken, { search: search || undefined, pageSize: 50 });
    if (result.ok) {
      if (kind === 'agents') setAgents(result.data as UltravoxAgentPage);
      else setVoices(result.data as UltravoxVoicePage);
    } else setMessage(result.detail);
    setBusy(null);
  }

  async function importAgent(agentId: string) {
    setBusy(`import:${agentId}`);
    setMessage(null);
    const result = await importUltravoxAgent(accessToken, agentId);
    if (result.ok) {
      setMessage(result.data.warnings.length
        ? t('importedWarnings', { count: result.data.warnings.length })
        : t('imported'));
      router.push(`/${locale}/voice-ai/agents/${result.data.agent_id}`);
    } else setMessage(result.detail);
    setBusy(null);
  }

  async function previewVoice(voiceId: string) {
    const url = ultravoxVoicePreviewUrl(voiceId);
    if (!url) return setMessage(t('backendMissing'));
    setBusy(`preview:${voiceId}`);
    const response = await fetch(url, {
      headers: { Authorization: `Bearer ${accessToken}` },
      cache: 'no-store',
    });
    if (!response.ok) setMessage(t('previewFailed'));
    else {
      const objectUrl = URL.createObjectURL(await response.blob());
      const audio = new Audio(objectUrl);
      audio.addEventListener('ended', () => URL.revokeObjectURL(objectUrl), { once: true });
      await audio.play();
    }
    setBusy(null);
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap gap-2 border-b border-border" role="tablist" aria-label={t('ariaLabel')}>
        {tabs.map((item) => (
          <button key={item} role="tab" aria-selected={tab === item} onClick={() => setTab(item)}
            className={`border-b-2 px-4 py-3 text-sm font-medium transition ${tab === item ? 'border-primary text-primary' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
            {t(`tabs.${item}`)}
          </button>
        ))}
      </div>

      {message && <div role="status" className="rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm">{message}</div>}

      {tab === 'connection' && (
        <VoiceIntegrationCard accessToken={accessToken} initialConfig={initialConfig} initialAgents={initialVoiceAgents} />
      )}

      {tab === 'agents' && (
        <section className="space-y-4" aria-labelledby="ultravox-agents-title">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div><h2 id="ultravox-agents-title" className="text-lg font-semibold">{t('agentsTitle')}</h2><p className="text-sm text-muted-foreground">{t('agentsHelp')}</p></div>
            <div className="flex gap-2"><input value={search} onChange={(event) => setSearch(event.target.value)} aria-label={t('search')} placeholder={t('search')} className="min-h-10 rounded-md border bg-background px-3 text-sm"/><Button variant="outline" onClick={() => reload('agents')} disabled={busy === 'agents'}>{busy === 'agents' ? <Loader2 className="size-4 animate-spin"/> : t('filter')}</Button></div>
          </div>
          {!active && <p className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950">{t('connectionRequired')}</p>}
          <div className="grid gap-3 lg:grid-cols-2">
            {agents?.results.map((agent) => (
              <article key={agent.agent_id} className="rounded-xl border bg-card p-5 shadow-sm">
                <div className="flex items-start justify-between gap-4"><div><h3 className="font-semibold">{agent.name}</h3><p className="mt-1 text-xs text-muted-foreground">{t('observedRevision', { revision: agent.published_revision_id ?? t('unpublished') })}</p></div><Bot className="size-5 text-primary"/></div>
                {agent.has_unsupported_client_tools && <p className="mt-3 flex gap-2 text-sm text-amber-700"><AlertTriangle className="mt-0.5 size-4 shrink-0"/>{t('blockedTools')}</p>}
                <div className="mt-4 flex flex-wrap gap-2"><Button size="sm" disabled={agent.has_unsupported_client_tools} onClick={() => router.push(`/${locale}/voice-ai/agents/new?management_mode=provider_managed&provider_agent_id=${encodeURIComponent(agent.agent_id)}&provider_agent_name=${encodeURIComponent(agent.name)}&observed_published_revision_id=${encodeURIComponent(agent.published_revision_id ?? '')}`)}><Link2 className="mr-2 size-4"/>{t('use')}</Button><Button size="sm" variant="outline" disabled={busy === `import:${agent.agent_id}`} onClick={() => importAgent(agent.agent_id)}>{busy === `import:${agent.agent_id}` ? <Loader2 className="mr-2 size-4 animate-spin"/> : null}{t('import')}</Button></div>
              </article>
            ))}
          </div>
        </section>
      )}

      {tab === 'voices' && (
        <section className="space-y-4" aria-labelledby="ultravox-voices-title">
          <div className="flex items-end justify-between gap-3"><div><h2 id="ultravox-voices-title" className="text-lg font-semibold">{t('voicesTitle')}</h2><p className="text-sm text-muted-foreground">{t('voicesHelp')}</p></div><Button variant="outline" onClick={() => reload('voices')} disabled={busy === 'voices'}>{t('refresh')}</Button></div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{voices?.results.map((voice) => <article key={voice.voice_id} className="rounded-xl border bg-card p-4"><div className="flex items-center justify-between"><div><h3 className="font-medium">{voice.name}</h3><p className="text-xs text-muted-foreground">{voice.language_label ?? voice.primary_language ?? t('unknownLanguage')} · {voice.ownership}</p></div><Volume2 className="size-5 text-primary"/></div><p className="mt-3 text-xs text-muted-foreground">{voice.billing_style === 'VOICE_BILLING_STYLE_EXTERNAL' ? t('externalBilling') : t('includedBilling')}</p><Button className="mt-4" size="sm" variant="outline" onClick={() => previewVoice(voice.voice_id)} disabled={busy === `preview:${voice.voice_id}`}><Play className="mr-2 size-4"/>{t('listen')}</Button></article>)}</div>
        </section>
      )}

      {tab === 'status' && (
        <section className="grid gap-4 sm:grid-cols-3"><div className="rounded-xl border p-5"><Radio className="size-5 text-primary"/><p className="mt-3 text-sm text-muted-foreground">{t('connection')}</p><p className="font-semibold">{active ? t('active') : t('notConfigured')}</p></div><div className="rounded-xl border p-5"><Bot className="size-5 text-primary"/><p className="mt-3 text-sm text-muted-foreground">{t('visibleAgents')}</p><p className="font-semibold">{agents?.total ?? 0}</p></div><div className="rounded-xl border p-5"><AlertTriangle className="size-5 text-amber-600"/><p className="mt-3 text-sm text-muted-foreground">{t('blockingCount')}</p><p className="font-semibold">{blockingTools}</p></div></section>
      )}
    </div>
  );
}
