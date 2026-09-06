'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, Bot, CheckCircle2, Save, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  archiveAgentAction,
  createAgentAction,
  createAgentNextDraftAction,
  publishAgentAction,
  updateAgentAction,
  updateAgentDraftAction,
} from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import { ActionDialog } from '@/components/crm/voice-experiences/ActionDialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AgentStatusBadge } from './AgentStatusBadge';
import type { VoiceAgentConfigResponse } from '@/types/crm';
import type {
  AgentBehavior,
  AgentConfirmationStrategy,
  AgentInterruptions,
  AgentResponse,
  AgentResponseStyle,
  AgentTurnDetection,
  AgentVersionResponse,
} from '@/types/agents';
import type { VoiceModelResponse, VoiceProviderResponse } from '@/types/voice-registry';

const FIELD_CLASS =
  'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

const DEFAULT_BEHAVIOR: AgentBehavior = {
  response_style: 'balanced',
  interruptions: 'balanced',
  turn_detection: 'automatic',
  confirmation_strategy: 'important_data',
  agent_first: true,
};

type FormState = {
  name: string;
  description: string;
  language: string;
  timezone: string;
  role: string;
  objective: string;
  system_prompt: string;
  greeting: string;
  closing: string;
  behavior: AgentBehavior;
  voice_agent_config_id: string;
  pipeline_type: 'realtime';
  provider: string;
  model: string;
};

function defaultForm(): FormState {
  return {
    name: '',
    description: '',
    language: 'es',
    timezone: 'America/Bogota',
    role: '',
    objective: '',
    system_prompt: '',
    greeting: '',
    closing: '',
    behavior: DEFAULT_BEHAVIOR,
    voice_agent_config_id: '',
    pipeline_type: 'realtime',
    provider: 'ultravox',
    model: 'ultravox',
  };
}

function toForm(agent: AgentResponse, draft: AgentVersionResponse): FormState {
  return {
    name: agent.name,
    description: agent.description ?? '',
    language: draft.language,
    timezone: draft.timezone,
    role: draft.instructions.role,
    objective: draft.instructions.objective,
    system_prompt: draft.instructions.system_prompt,
    greeting: draft.instructions.greeting,
    closing: draft.instructions.closing,
    behavior: draft.behavior,
    voice_agent_config_id: draft.voice_agent_config_id ?? '',
    pipeline_type: draft.runtime_binding.pipeline_type,
    provider: draft.runtime_binding.realtime.provider,
    model: draft.runtime_binding.realtime.model,
  };
}

type Tab = 'general' | 'behavior' | 'voice' | 'versions';

type Props = {
  mode: 'create' | 'edit';
  locale: string;
  canEdit: boolean;
  voiceAgents: VoiceAgentConfigResponse[];
  providers: VoiceProviderResponse[];
  models: VoiceModelResponse[];
  initialAgent?: AgentResponse | null;
  initialDraft?: AgentVersionResponse | null;
  initialVersions?: AgentVersionResponse[];
};

export function AgentBuilder({
  mode,
  locale,
  canEdit,
  voiceAgents,
  providers,
  models,
  initialAgent = null,
  initialDraft = null,
  initialVersions = [],
}: Props) {
  const t = useTranslations('crm.agentBuilder');
  const router = useRouter();
  const [agent, setAgent] = useState(initialAgent);
  const [draft, setDraft] = useState(initialDraft);
  const [versions, setVersions] = useState(initialVersions);
  const [tab, setTab] = useState<Tab>('general');
  const [form, setForm] = useState<FormState>(() =>
    agent && draft ? toForm(agent, draft) : defaultForm()
  );
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [branching, setBranching] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const archived = agent?.status === 'archived';
  const editable = canEdit && !archived;
  const hasDraft = draft !== null;

  const tabs = useMemo(
    () =>
      [
        { key: 'general' as const, label: t('tabs.general') },
        { key: 'behavior' as const, label: t('tabs.behavior') },
        { key: 'voice' as const, label: t('tabs.voice') },
        ...(mode === 'edit' ? [{ key: 'versions' as const, label: t('tabs.versions') }] : []),
      ],
    [t, mode]
  );

  function setBehavior<K extends keyof AgentBehavior>(key: K, value: AgentBehavior[K]) {
    setForm((current) => ({ ...current, behavior: { ...current.behavior, [key]: value } }));
    setSaved(false);
  }

  function field<K extends keyof FormState>(key: K) {
    return {
      value: form[key] as string,
      onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
        setForm((current) => ({ ...current, [key]: e.target.value }));
        setSaved(false);
      },
    };
  }

  async function handleCreate() {
    setSaving(true);
    setServerError(null);
    const result = await createAgentAction(locale, {
      name: form.name,
      description: form.description || null,
      language: form.language,
      timezone: form.timezone,
      instructions: {
        role: form.role,
        objective: form.objective,
        system_prompt: form.system_prompt,
        greeting: form.greeting,
        closing: form.closing,
      },
      behavior: form.behavior,
      voice_agent_config_id: form.voice_agent_config_id || null,
      pipeline_type: form.pipeline_type,
      provider: form.provider,
      model: form.model,
    });
    setSaving(false);
    if (!result.ok) {
      setServerError(t(result.status === 422 ? 'errors.validation' : 'errors.generic'));
      return;
    }
    router.push(`/${locale}/voice-ai/agents/${result.data.id}`);
  }

  async function handleSaveDraft() {
    if (!agent || !draft) return;
    setSaving(true);
    setServerError(null);
    const [agentResult, draftResult] = await Promise.all([
      updateAgentAction(locale, agent.id, {
        name: form.name,
        description: form.description || null,
      }),
      updateAgentDraftAction(locale, agent.id, {
        language: form.language,
        timezone: form.timezone,
        instructions: {
          role: form.role,
          objective: form.objective,
          system_prompt: form.system_prompt,
          greeting: form.greeting,
          closing: form.closing,
        },
        behavior: form.behavior,
        voice_agent_config_id: form.voice_agent_config_id || null,
        pipeline_type: form.pipeline_type,
        provider: form.provider,
        model: form.model,
      }),
    ]);
    setSaving(false);
    if (!agentResult.ok || !draftResult.ok) {
      const failed = !agentResult.ok ? agentResult : draftResult;
      setServerError(t(!failed.ok && failed.status === 422 ? 'errors.validation' : 'errors.generic'));
      return;
    }
    setAgent(agentResult.data);
    setDraft(draftResult.data);
    setSaved(true);
  }

  async function handlePublish() {
    if (!agent) return;
    setPublishing(true);
    setServerError(null);
    const result = await publishAgentAction(locale, agent.id);
    setPublishing(false);
    if (!result.ok) {
      setServerError(
        t(result.status === 422 ? 'errors.publishValidation' : 'errors.generic')
      );
      return;
    }
    setAgent(result.data);
    setDraft(null);
    setVersions((current) =>
      current.map((version) =>
        version.id === result.data.published_version_id
          ? { ...version, status: 'published', published_at: new Date().toISOString() }
          : version.status === 'published'
            ? { ...version, status: 'superseded' }
            : version
      )
    );
  }

  async function handleCreateDraft() {
    if (!agent) return;
    setBranching(true);
    setServerError(null);
    const result = await createAgentNextDraftAction(locale, agent.id);
    setBranching(false);
    if (!result.ok) {
      setServerError(t('errors.generic'));
      return;
    }
    setDraft(result.data);
    setVersions((current) => [result.data, ...current]);
    setForm(toForm(agent, result.data));
    setTab('general');
  }

  async function handleArchive() {
    if (!agent) return;
    const result = await archiveAgentAction(locale, agent.id);
    if (result.ok) {
      setAgent(result.data);
      setDraft(null);
    }
  }

  if (mode === 'create') {
    return (
      <div className="space-y-6">
        <GeneralFields field={field} disabled={!canEdit} t={t} />
        {serverError ? <ErrorBanner message={serverError} /> : null}
        <div className="flex justify-end">
          <Button onClick={handleCreate} disabled={!canEdit || saving || !form.name.trim()}>
            <Sparkles className="mr-2 size-4" aria-hidden="true" />
            {t('createAgent')}
          </Button>
        </div>
      </div>
    );
  }

  if (!agent) return null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-5">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Bot className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-xl font-bold text-foreground">{agent.name}</h1>
            <AgentStatusBadge status={agent.status} />
          </div>
        </div>
        {editable && !archived ? (
          <ActionDialog
            trigger={
              <Button type="button" variant="ghost" size="sm">
                <Archive className="mr-1.5 size-4" aria-hidden="true" />
                {t('actions.archive')}
              </Button>
            }
            title={t('confirm.archive.title')}
            description={t('confirm.archive.description')}
            confirmLabel={t('actions.archive')}
            cancelLabel={t('common.cancel')}
            destructive
            onConfirm={handleArchive}
          />
        ) : null}
      </div>

      <div className="flex flex-wrap gap-2 border-b border-border pb-3">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition ${
              tab === item.key
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-muted/70'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {serverError ? <ErrorBanner message={serverError} /> : null}

      {!hasDraft && tab !== 'versions' ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 p-8 text-center">
            <p className="text-sm text-muted-foreground">{t('noDraft.description')}</p>
            {editable ? (
              <Button onClick={handleCreateDraft} disabled={branching}>
                {t('noDraft.cta')}
              </Button>
            ) : null}
          </CardContent>
        </Card>
      ) : (
        <>
          {tab === 'general' ? (
            <GeneralFields field={field} disabled={!editable || !hasDraft} t={t} />
          ) : null}

          {tab === 'behavior' ? (
            <BehaviorFields
              behavior={form.behavior}
              onChange={setBehavior}
              disabled={!editable || !hasDraft}
              t={t}
            />
          ) : null}

          {tab === 'voice' ? (
            <VoiceFields
              pipelineType={form.pipeline_type}
              provider={form.provider}
              model={form.model}
              providers={providers}
              models={models}
              voiceAgentConfigId={form.voice_agent_config_id}
              voiceAgents={voiceAgents}
              disabled={!editable || !hasDraft}
              onProviderChange={(value) => {
                setForm((current) => ({ ...current, provider: value }));
                setSaved(false);
              }}
              onModelChange={(value) => {
                setForm((current) => ({ ...current, model: value }));
                setSaved(false);
              }}
              onVoiceAgentConfigChange={(value) => {
                setForm((current) => ({ ...current, voice_agent_config_id: value }));
                setSaved(false);
              }}
              t={t}
            />
          ) : null}

          {tab === 'versions' ? (
            <VersionsPanel versions={versions} publishedVersionId={agent.published_version_id} t={t} />
          ) : null}

          {tab !== 'versions' && hasDraft && editable ? (
            <div className="flex flex-wrap items-center justify-end gap-3">
              {saved ? (
                <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
                  <CheckCircle2 className="size-4 text-cyan-500" aria-hidden="true" />
                  {t('draftSaved')}
                </span>
              ) : null}
              <Button variant="outline" onClick={handleSaveDraft} disabled={saving}>
                <Save className="mr-2 size-4" aria-hidden="true" />
                {t('saveDraft')}
              </Button>
              <Button onClick={handlePublish} disabled={publishing || !form.system_prompt.trim()}>
                {t('publish')}
              </Button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
      {message}
    </p>
  );
}

function GeneralFields({
  field,
  disabled,
  t,
}: {
  field: <K extends keyof FormState>(
    key: K
  ) => { value: string; onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void };
  disabled: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('tabs.general')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <span className="font-medium text-foreground">{t('fields.name')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('name')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <span className="font-medium text-foreground">{t('fields.description')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('description')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.language')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('language')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.timezone')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('timezone')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.role')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('role')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.objective')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('objective')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <span className="font-medium text-foreground">{t('fields.systemPrompt')}</span>
          <textarea className={`${FIELD_CLASS} min-h-32`} disabled={disabled} {...field('system_prompt')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.greeting')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('greeting')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.closing')}</span>
          <input className={FIELD_CLASS} disabled={disabled} {...field('closing')} />
        </label>
      </CardContent>
    </Card>
  );
}

function BehaviorFields({
  behavior,
  onChange,
  disabled,
  t,
}: {
  behavior: AgentBehavior;
  onChange: <K extends keyof AgentBehavior>(key: K, value: AgentBehavior[K]) => void;
  disabled: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  const responseStyles: AgentResponseStyle[] = ['precise', 'balanced', 'creative'];
  const interruptions: AgentInterruptions[] = ['conservative', 'balanced', 'responsive'];
  const turnDetections: AgentTurnDetection[] = ['automatic', 'conservative', 'balanced', 'responsive'];
  const confirmations: AgentConfirmationStrategy[] = ['important_data', 'always', 'never'];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('tabs.behavior')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.responseStyle')}</span>
          <select
            className={FIELD_CLASS}
            disabled={disabled}
            value={behavior.response_style}
            onChange={(e) => onChange('response_style', e.target.value as AgentResponseStyle)}
          >
            {responseStyles.map((value) => (
              <option key={value} value={value}>
                {t(`behaviorOptions.responseStyle.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.interruptions')}</span>
          <select
            className={FIELD_CLASS}
            disabled={disabled}
            value={behavior.interruptions}
            onChange={(e) => onChange('interruptions', e.target.value as AgentInterruptions)}
          >
            {interruptions.map((value) => (
              <option key={value} value={value}>
                {t(`behaviorOptions.interruptions.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.turnDetection')}</span>
          <select
            className={FIELD_CLASS}
            disabled={disabled}
            value={behavior.turn_detection}
            onChange={(e) => onChange('turn_detection', e.target.value as AgentTurnDetection)}
          >
            {turnDetections.map((value) => (
              <option key={value} value={value}>
                {t(`behaviorOptions.turnDetection.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-medium text-foreground">{t('fields.confirmationStrategy')}</span>
          <select
            className={FIELD_CLASS}
            disabled={disabled}
            value={behavior.confirmation_strategy}
            onChange={(e) =>
              onChange('confirmation_strategy', e.target.value as AgentConfirmationStrategy)
            }
          >
            {confirmations.map((value) => (
              <option key={value} value={value}>
                {t(`behaviorOptions.confirmationStrategy.${value}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input
            type="checkbox"
            disabled={disabled}
            checked={behavior.agent_first}
            onChange={(e) => onChange('agent_first', e.target.checked)}
            className="size-4 rounded border-input"
          />
          <span className="font-medium text-foreground">{t('fields.agentFirst')}</span>
        </label>
      </CardContent>
    </Card>
  );
}

function VoiceFields({
  pipelineType,
  provider,
  model,
  providers,
  models,
  voiceAgentConfigId,
  voiceAgents,
  disabled,
  onProviderChange,
  onModelChange,
  onVoiceAgentConfigChange,
  t,
}: {
  pipelineType: 'realtime';
  provider: string;
  model: string;
  providers: VoiceProviderResponse[];
  models: VoiceModelResponse[];
  voiceAgentConfigId: string;
  voiceAgents: VoiceAgentConfigResponse[];
  disabled: boolean;
  onProviderChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onVoiceAgentConfigChange: (value: string) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const realtimeModels = models.filter((m) => m.model_type === 'realtime' && m.provider_key === provider);
  const selectedModel = models.find((m) => m.provider_key === provider && m.key === model) ?? null;
  const activeCapabilities = selectedModel
    ? Object.entries(selectedModel.capabilities).filter(([, enabled]) => enabled)
    : [];

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.pipelineType')}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <span
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              pipelineType === 'realtime'
                ? 'bg-primary text-primary-foreground'
                : 'border border-dashed border-border text-muted-foreground'
            }`}
          >
            {t('voice.speechToSpeech')}
          </span>
          <span className="rounded-full border border-dashed border-border px-3 py-1 text-xs text-muted-foreground">
            {t('voice.modular')} · {t('voice.comingSoon')}
          </span>
          <span className="rounded-full border border-dashed border-border px-3 py-1 text-xs text-muted-foreground">
            {t('voice.hybrid')} · {t('voice.comingSoon')}
          </span>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.providerModel')}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('voice.provider')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled}
              value={provider}
              onChange={(e) => onProviderChange(e.target.value)}
            >
              {providers.map((p) => (
                <option key={p.key} value={p.key} disabled={p.status !== 'active'}>
                  {p.name}
                  {p.status !== 'active' ? ` (${t('voice.comingSoon')})` : ''}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('voice.model')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled || realtimeModels.length === 0}
              value={model}
              onChange={(e) => onModelChange(e.target.value)}
            >
              {realtimeModels.length === 0 ? (
                <option value="">{t('voice.noModels')}</option>
              ) : (
                realtimeModels.map((m) => (
                  <option key={m.id} value={m.key} disabled={m.implementation_status !== 'available'}>
                    {m.name}
                    {m.implementation_status !== 'available' ? ` (${t('voice.comingSoon')})` : ''}
                  </option>
                ))
              )}
            </select>
          </label>
        </CardContent>
        {activeCapabilities.length > 0 ? (
          <CardContent className="flex flex-wrap gap-2 pt-0">
            {activeCapabilities.map(([key]) => (
              <span
                key={key}
                className="rounded-full bg-cyan-500/10 px-2.5 py-1 text-xs font-medium text-cyan-700 dark:text-cyan-300"
              >
                {t(`voice.capabilities.${key}`)}
              </span>
            ))}
          </CardContent>
        ) : null}
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.linkTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="font-medium text-foreground">{t('voice.linkLabel')}</span>
            <select
              className={FIELD_CLASS}
              disabled={disabled}
              value={voiceAgentConfigId}
              onChange={(e) => onVoiceAgentConfigChange(e.target.value)}
            >
              <option value="">{t('voice.linkNone')}</option>
              {voiceAgents.map((va) => (
                <option key={va.id} value={va.id}>
                  {va.display_name}
                </option>
              ))}
            </select>
            <span className="text-xs text-muted-foreground">{t('voice.linkHelp')}</span>
          </label>
        </CardContent>
      </Card>
    </div>
  );
}

function VersionsPanel({
  versions,
  publishedVersionId,
  t,
}: {
  versions: AgentVersionResponse[];
  publishedVersionId: string | null;
  t: ReturnType<typeof useTranslations>;
}) {
  if (versions.length === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-sm text-muted-foreground">{t('versions.empty')}</CardContent>
      </Card>
    );
  }
  return (
    <Card>
      <CardContent className="divide-y divide-border p-0">
        {[...versions]
          .sort((a, b) => b.version - a.version)
          .map((version) => (
            <div key={version.id} className="flex items-center justify-between gap-3 p-4">
              <div>
                <p className="font-semibold text-foreground">
                  V{version.version}
                  {version.id === publishedVersionId ? ` · ${t('versions.current')}` : ''}
                </p>
                <p className="text-xs text-muted-foreground">
                  {version.published_at
                    ? t('versions.publishedAt', {
                        date: new Date(version.published_at).toLocaleDateString(),
                      })
                    : t('versions.neverPublished')}
                </p>
              </div>
              <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                {t(`versionStatus.${version.status}`)}
              </span>
            </div>
          ))}
      </CardContent>
    </Card>
  );
}
