'use client';

import { voicePreviewErrorKey } from '@/lib/voice-preview-error';
import type { VoicePreviewMediaType } from '@/lib/voice-preview-media-type';

import { useMemo, useState, type ChangeEvent } from 'react';
import { useRouter } from 'next/navigation';
import { Archive, Bot, CheckCircle2, Loader2, Play, Save, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  archiveAgentAction,
  createAgentAction,
  createAgentNextDraftAction,
  deleteAgentAction,
  fetchAgentVersionsAction,
  previewExternalVoiceAction,
  previewProviderVoiceAction,
  publishAgentAction,
  unpublishAgentAction,
  updateAgentDraftAction,
} from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import { ActionDialog } from '@/components/crm/voice-experiences/ActionDialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AgentModelSection } from './AgentModelSection';
import { AgentFieldLabel } from './AgentFieldLabel';
import { AgentStatusBadge } from './AgentStatusBadge';
import { AgentToolsSection } from './AgentToolsSection';
import { AgentVoiceTest } from './AgentVoiceTest';
import type { VoiceAgentConfigResponse } from '@/types/crm';
import type {
  AgentBehavior,
  AgentConfirmationStrategy,
  AgentInterruptions,
  AgentModelSettings,
  AgentResponse,
  AgentResponseStyle,
  AgentToolCatalogEntry,
  AgentTurnDetection,
  AgentVersionResponse,
  AgentVoiceConfig,
} from '@/types/agents';
import type { VoiceModelResponse, VoiceProviderResponse } from '@/types/voice-registry';
import type { UltravoxAgentSummary, UltravoxVoiceSummary } from '@/types/ultravox-admin';

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
  management_mode: 'serviglobal_managed' | 'provider_managed';
  provider_agent_id: string;
  observed_published_revision_id: string;
  provider_agent_name: string;
  voice_mode: 'provider' | 'provider_external';
  voice_id: string;
  voice_model: string;
  voice_speed: string;
  voice_stability: string;
  voice_similarity_boost: string;
  voice_use_speaker_boost: boolean;
  // Raw string form of provider/model runtime settings (e.g. temperature),
  // keyed by the VoiceModelResponse.parameters key. Converted to typed
  // values only at submit time -- see buildModelSettingsPayload.
  model_settings: Record<string, string>;
  // Keys of AgentToolCatalogEntry the agent has enabled. `config` is
  // always {} for both V1 tools (see types/agents.ts::AgentToolBinding).
  enabled_tools: string[];
};

const DEFAULT_EXTERNAL_VOICE_MODEL = 'eleven_turbo_v2_5';

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
    management_mode: 'serviglobal_managed',
    provider_agent_id: '',
    observed_published_revision_id: '',
    provider_agent_name: '',
    voice_mode: 'provider',
    voice_id: '',
    voice_model: DEFAULT_EXTERNAL_VOICE_MODEL,
    voice_speed: '',
    voice_stability: '',
    voice_similarity_boost: '',
    voice_use_speaker_boost: true,
    model_settings: {},
    enabled_tools: [],
  };
}

function toForm(agent: AgentResponse, draft: AgentVersionResponse): FormState {
  const voice = draft.runtime_binding.realtime.voice ?? null;
  const settings = (voice?.settings ?? {}) as Record<string, unknown>;
  const modelSettings = (draft.runtime_binding.realtime.settings ?? {}) as Record<string, unknown>;
  const model_settings: Record<string, string> = {};
  for (const [key, value] of Object.entries(modelSettings)) {
    model_settings[key] = typeof value === 'boolean' ? String(value) : String(value ?? '');
  }
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
    management_mode: draft.runtime_binding.realtime.management_mode ?? 'serviglobal_managed',
    provider_agent_id: draft.runtime_binding.realtime.provider_agent?.agent_id ?? '',
    observed_published_revision_id: draft.runtime_binding.realtime.provider_agent?.observed_published_revision_id ?? '',
    provider_agent_name: draft.runtime_binding.realtime.provider_agent?.agent_id ?? '',
    voice_mode: voice?.mode ?? 'provider',
    voice_id: voice?.voice_id ?? '',
    voice_model: typeof settings.model === 'string' ? settings.model : DEFAULT_EXTERNAL_VOICE_MODEL,
    voice_speed: typeof settings.speed === 'number' ? String(settings.speed) : '',
    voice_stability: typeof settings.stability === 'number' ? String(settings.stability) : '',
    voice_similarity_boost: typeof settings.similarity_boost === 'number' ? String(settings.similarity_boost) : '',
    voice_use_speaker_boost: typeof settings.use_speaker_boost === 'boolean' ? settings.use_speaker_boost : true,
    model_settings,
    enabled_tools: (draft.runtime_binding.tools ?? []).filter((tool) => tool.enabled).map((tool) => tool.key),
  };
}

/** Builds the AgentVoiceConfig the backend expects from the flat form
 * fields, or null when no voice_id was entered (the agent then falls back
 * to the runtime default / legacy voice_agent_config_id link -- see
 * AgentCompilerService.compile()). Only the fields relevant to the current
 * voice_mode are serialized; the inactive path's stale field values are
 * simply never read. */
function buildVoicePayload(form: FormState): AgentVoiceConfig | null {
  const voiceId = form.voice_id.trim();
  if (!voiceId) return null;
  if (form.voice_mode === 'provider') {
    return { mode: 'provider', provider: form.provider, voice_id: voiceId, settings: {} };
  }
  const settings: NonNullable<AgentVoiceConfig['settings']> = {
    use_speaker_boost: form.voice_use_speaker_boost,
  };
  if (form.voice_model.trim()) settings.model = form.voice_model.trim();
  if (form.voice_speed.trim()) settings.speed = Number(form.voice_speed);
  if (form.voice_stability.trim()) settings.stability = Number(form.voice_stability);
  if (form.voice_similarity_boost.trim()) settings.similarity_boost = Number(form.voice_similarity_boost);
  return { mode: 'provider_external', provider: 'elevenlabs', voice_id: voiceId, settings };
}

/** Converts the raw string form_settings back into typed values, and drops
 * any key the currently selected model doesn't declare as supported=true --
 * switching provider/model away from one that supported a parameter must
 * not silently resend a now-unsupported value. */
function buildModelSettingsPayload(form: FormState, selectedModel: VoiceModelResponse | null): AgentModelSettings {
  const settings: AgentModelSettings = {};
  if (!selectedModel) return settings;
  for (const [key, spec] of Object.entries(selectedModel.parameters)) {
    if (!spec.supported) continue;
    const raw = form.model_settings[key];
    if (raw === undefined || raw === '') continue;
    if (spec.type === 'boolean') {
      settings[key] = raw === 'true';
    } else if (spec.type === 'number' || spec.type === 'integer') {
      const parsed = Number(raw);
      if (!Number.isNaN(parsed)) settings[key] = parsed;
    } else {
      settings[key] = raw;
    }
  }
  return settings;
}

/** Only ever binds tools the catalog still reports as `available` -- an
 * enabled key that became unavailable (or was removed from the Registry)
 * between load and save is silently dropped rather than resent, mirroring
 * buildModelSettingsPayload's "never resend what's no longer valid" rule. */
function buildToolsPayload(form: FormState, catalog: AgentToolCatalogEntry[]) {
  const availableKeys = new Set(catalog.filter((tool) => tool.available).map((tool) => tool.key));
  return form.enabled_tools
    .filter((key) => availableKeys.has(key))
    .map((key) => ({ key, enabled: true, config: {} }));
}

/** Publish-time errors carry a stable code as (a prefix of) the response
 * detail -- see AgentService._publish_tools_preflight/_publish_voice_preflight
 * on the backend. Draft-save validation errors stay generic (see
 * VoiceSelectionService/voice_registry.validate_model_settings, which
 * raise prose messages for inline form issues, not stable codes) -- this
 * mapping only covers the codes a publish preflight can actually raise. */
const PUBLISH_ERROR_CODE_KEYS: Record<string, string> = {
  tool_not_found: 'errors.toolNotFound',
  tool_not_available: 'errors.toolNotAvailable',
  tool_integration_not_configured: 'errors.toolIntegrationNotConfigured',
  voice_not_accessible: 'errors.voiceNotAccessible',
  external_tts_credentials_unavailable: 'errors.voiceCredentialsUnavailable',
  provider_credentials_unavailable: 'errors.voiceCredentialsUnavailable',
};

function publishErrorMessage(t: ReturnType<typeof useTranslations>, detail: string | undefined): string {
  const code = Object.keys(PUBLISH_ERROR_CODE_KEYS).find((known) => detail?.startsWith(known));
  return code ? t(PUBLISH_ERROR_CODE_KEYS[code]) : t('errors.publishValidation');
}

async function playAudioBase64(base64: string, mediaType: VoicePreviewMediaType) {
  const audio = new Audio(`data:${mediaType};base64,${base64}`);
  try {
    await audio.play();
  } catch {
    // Autoplay can be blocked by the browser; the user already sees the
    // "Escuchar"/"Probar voz" button reflect the busy state, no further
    // recovery needed here.
  }
}

type Tab = 'general' | 'behavior' | 'model' | 'voice' | 'tools' | 'versions';

type Props = {
  mode: 'create' | 'edit';
  locale: string;
  canEdit: boolean;
  voiceAgents: VoiceAgentConfigResponse[];
  providers: VoiceProviderResponse[];
  models: VoiceModelResponse[];
  providerVoices?: UltravoxVoiceSummary[];
  toolCatalog?: AgentToolCatalogEntry[];
  initialAgent?: AgentResponse | null;
  initialDraft?: AgentVersionResponse | null;
  initialVersions?: AgentVersionResponse[];
  initialProviderAgent?: {
    agentId: string;
    name: string;
    observedPublishedRevisionId: string | null;
  } | null;
  providerAgents?: UltravoxAgentSummary[];
};

export function AgentBuilder({
  mode,
  locale,
  canEdit,
  voiceAgents,
  providers,
  models,
  providerVoices = [],
  toolCatalog = [],
  initialAgent = null,
  initialDraft = null,
  initialVersions = [],
  initialProviderAgent = null,
  providerAgents = [],
}: Props) {
  const t = useTranslations('crm.agentBuilder');
  const router = useRouter();
  const [agent, setAgent] = useState(initialAgent);
  const [draft, setDraft] = useState(initialDraft);
  const [versions, setVersions] = useState(initialVersions);
  const [tab, setTab] = useState<Tab>('general');
  const [form, setForm] = useState<FormState>(() =>
    agent && draft
      ? toForm(agent, draft)
      : initialProviderAgent
        ? {
            ...defaultForm(),
            name: initialProviderAgent.name,
            model: 'ultravox-v0.7',
            management_mode: 'provider_managed',
            provider_agent_id: initialProviderAgent.agentId,
            observed_published_revision_id: initialProviderAgent.observedPublishedRevisionId ?? '',
            provider_agent_name: initialProviderAgent.name,
          }
        : defaultForm()
  );
  const [saving, setSaving] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [branching, setBranching] = useState(false);
  const [lifecycleBusy, setLifecycleBusy] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [previewBusy, setPreviewBusy] = useState<'provider' | 'provider_external' | null>(null);
  // Ephemeral, UI-only: the backend never records whether a voice was
  // previewed (see Fase D "no persistir estado de preview"). This only
  // drives a non-blocking reminder banner and resets whenever the external
  // voice config actually changes, since a stale preview no longer proves
  // anything about the current settings.
  const [previewedExternalVoice, setPreviewedExternalVoice] = useState(false);

  const archived = agent?.status === 'archived';
  const editable = canEdit && !archived;
  const hasDraft = draft !== null;
  const selectedModel = models.find((m) => m.provider_key === form.provider && m.key === form.model) ?? null;
  const publishedVersion = versions.find((version) => version.id === agent?.published_version_id) ?? null;

  const tabs = useMemo(
    () =>
      [
        { key: 'general' as const, label: t('tabs.general') },
        { key: 'behavior' as const, label: t('tabs.behavior') },
        { key: 'model' as const, label: t('tabs.model') },
        { key: 'voice' as const, label: t('tabs.voice') },
        { key: 'tools' as const, label: t('tabs.tools') },
        ...(mode === 'edit' ? [{ key: 'versions' as const, label: t('tabs.versions') }] : []),
      ],
    [t, mode]
  );

  function setBehavior<K extends keyof AgentBehavior>(key: K, value: AgentBehavior[K]) {
    setForm((current) => ({ ...current, behavior: { ...current.behavior, [key]: value } }));
    setSaved(false);
  }

  function setToolEnabled(key: string, toolEnabled: boolean) {
    setForm((current) => ({
      ...current,
      enabled_tools: toolEnabled
        ? [...current.enabled_tools, key]
        : current.enabled_tools.filter((existing) => existing !== key),
    }));
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

  function setVoiceField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setSaved(false);
    setPreviewedExternalVoice(false);
  }

  function setModelSettingText(key: string, value: string) {
    setForm((current) => ({ ...current, model_settings: { ...current.model_settings, [key]: value } }));
    setSaved(false);
  }

  function setModelSettingBoolean(key: string, value: boolean) {
    setForm((current) => ({ ...current, model_settings: { ...current.model_settings, [key]: String(value) } }));
    setSaved(false);
  }

  async function handlePreviewProviderVoice() {
    const voiceId = form.voice_id.trim();
    if (!voiceId) return;
    setPreviewBusy('provider');
    setServerError(null);
    const result = await previewProviderVoiceAction(form.provider, voiceId);
    setPreviewBusy(null);
    if (!result.ok) {
      setServerError(t(voicePreviewErrorKey(result)));
      return;
    }
    await playAudioBase64(result.audioBase64, result.mediaType);
  }

  async function handlePreviewExternalVoice() {
    const voice = buildVoicePayload(form);
    if (!voice || voice.mode !== 'provider_external') return;
    setPreviewBusy('provider_external');
    setServerError(null);
    const result = await previewExternalVoiceAction('ultravox', voice);
    setPreviewBusy(null);
    if (!result.ok) {
      setServerError(t(voicePreviewErrorKey(result)));
      return;
    }
    setPreviewedExternalVoice(true);
    await playAudioBase64(result.audioBase64, result.mediaType);
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
      management_mode: form.management_mode,
      provider_agent: form.management_mode === 'provider_managed' ? {
        agent_id: form.provider_agent_id,
        observed_published_revision_id: form.observed_published_revision_id || null,
      } : null,
      voice: form.management_mode === 'provider_managed' ? null : buildVoicePayload(form),
      settings: form.management_mode === 'provider_managed' ? {} : buildModelSettingsPayload(form, selectedModel),
      tools: form.management_mode === 'provider_managed' ? [] : buildToolsPayload(form, toolCatalog),
    });
    setSaving(false);
    if (!result.ok) {
      setServerError(t(result.status === 422 ? 'errors.validation' : 'errors.generic'));
      return;
    }
    router.push(`/${locale}/voice-ai/agents/${result.data.id}`);
  }

  function buildDraftPayload() {
    return {
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
      management_mode: form.management_mode,
      provider_agent: form.management_mode === 'provider_managed' ? {
        agent_id: form.provider_agent_id,
        observed_published_revision_id: form.observed_published_revision_id || null,
      } : null,
      voice: form.management_mode === 'provider_managed' ? null : buildVoicePayload(form),
      settings: form.management_mode === 'provider_managed' ? {} : buildModelSettingsPayload(form, selectedModel),
      tools: form.management_mode === 'provider_managed' ? [] : buildToolsPayload(form, toolCatalog),
    };
  }

  async function handleSaveDraft() {
    if (!agent || !draft) return;
    setSaving(true);
    setServerError(null);
    const result = await updateAgentDraftAction(locale, agent.id, buildDraftPayload());
    setSaving(false);
    if (!result.ok) {
      setServerError(t(result.status === 422 ? 'errors.validation' : 'errors.generic'));
      return;
    }
    setAgent((current) =>
      current
        ? { ...current, name: result.data.identity.name, description: result.data.identity.description ?? null }
        : current
    );
    setDraft(result.data);
    setSaved(true);
  }

  async function handlePublish() {
    if (!agent || !draft) return;
    setPublishing(true);
    setServerError(null);
    // Always save the on-screen form as the draft first, then publish
    // exactly that saved version id -- the user should never be able to
    // publish stale content just by skipping "Guardar".
    const draftResult = await updateAgentDraftAction(locale, agent.id, buildDraftPayload());
    if (!draftResult.ok) {
      setPublishing(false);
      setServerError(t(draftResult.status === 422 ? 'errors.validation' : 'errors.generic'));
      return;
    }
    const publishResult = await publishAgentAction(locale, agent.id, draftResult.data.id);
    setPublishing(false);
    if (!publishResult.ok) {
      setServerError(
        publishResult.status === 422 ? publishErrorMessage(t, publishResult.detail) : t('errors.generic')
      );
      return;
    }
    setAgent(publishResult.data);
    setDraft(null);
    setSaved(false);
    setVersions((current) =>
      current.map((version) =>
        version.id === publishResult.data.published_version_id
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
    setLifecycleBusy(true);
    setServerError(null);
    const result = await archiveAgentAction(locale, agent.id);
    setLifecycleBusy(false);
    if (result.ok) {
      setAgent(result.data);
      setDraft(null);
    } else {
      setServerError(t(result.status === 409 ? 'errors.conflict' : 'errors.generic'));
    }
  }

  async function handleUnpublish() {
    if (!agent) return;
    setLifecycleBusy(true);
    setServerError(null);
    const result = await unpublishAgentAction(locale, agent.id);
    if (!result.ok) {
      setLifecycleBusy(false);
      setServerError(t(result.status === 409 ? 'errors.conflict' : 'errors.generic'));
      return;
    }
    setAgent(result.data);
    const versionsResult = await fetchAgentVersionsAction(agent.id);
    setLifecycleBusy(false);
    if (!versionsResult.ok) {
      setServerError(t('errors.generic'));
      return;
    }
    const editableDraft =
      versionsResult.data.find((version) => version.id === result.data.draft_version_id) ?? null;
    setDraft(editableDraft);
    setVersions(versionsResult.data);
    if (editableDraft) setForm(toForm(result.data, editableDraft));
    setSaved(false);
    setTab('general');
  }

  async function handleDelete() {
    if (!agent) return;
    setLifecycleBusy(true);
    setServerError(null);
    const result = await deleteAgentAction(locale, agent.id);
    if (!result.ok) {
      setLifecycleBusy(false);
      setServerError(t(
        result.detail === 'agent_delete_room_close_failed' ? 'errors.deleteRoomCloseFailed'
          : result.detail === 'agent_delete_session_dispatching' ? 'errors.deleteDispatching'
            : result.detail === 'agent_delete_session_unverified' ? 'errors.deleteSessionUnverified'
          : result.detail === 'agent_delete_requires_archived' ? 'errors.deleteRequiresArchived'
            : result.status === 409 ? 'errors.deleteConflict' : 'errors.generic'
      ));
      return;
    }
    router.push(`/${locale}/voice-ai/agents`);
    router.refresh();
  }

  if (mode === 'create') {
    return (
      <div className="space-y-6">
        <GeneralFields field={field} disabled={!canEdit} providerManaged={form.management_mode === 'provider_managed'} t={t} />
        <AgentModelSection
          pipelineType={form.pipeline_type}
          provider={form.provider}
          model={form.model}
          providers={providers}
          models={models}
          managementMode={form.management_mode}
          providerAgentId={form.provider_agent_id}
          providerAgentName={form.provider_agent_name}
          observedRevisionId={form.observed_published_revision_id}
          currentRevisionId={providerAgents.find((item) => item.agent_id === form.provider_agent_id)?.published_revision_id ?? null}
          hasBlockingTools={providerAgents.find((item) => item.agent_id === form.provider_agent_id)?.has_unsupported_client_tools ?? false}
          modelSettings={form.model_settings}
          disabled={!canEdit}
          onManagementModeChange={(value) => setForm((current) => ({ ...current, management_mode: value, model: value === 'provider_managed' ? 'ultravox-v0.7' : 'ultravox' }))}
          onProviderChange={(value) => setForm((current) => ({ ...current, provider: value }))}
          onModelChange={(value) => setForm((current) => ({ ...current, model: value }))}
          onModelSettingTextChange={setModelSettingText}
          onModelSettingBooleanChange={setModelSettingBoolean}
          t={t}
        />
        <VoiceFields
          managementMode={form.management_mode}
          providerVoices={providerVoices}
          voiceAgentConfigId={form.voice_agent_config_id}
          voiceAgents={voiceAgents}
          voiceMode={form.voice_mode}
          voiceId={form.voice_id}
          voiceModel={form.voice_model}
          voiceSpeed={form.voice_speed}
          voiceStability={form.voice_stability}
          voiceSimilarityBoost={form.voice_similarity_boost}
          voiceUseSpeakerBoost={form.voice_use_speaker_boost}
          previewBusy={previewBusy}
          previewedExternalVoice={previewedExternalVoice}
          disabled={!canEdit}
          onVoiceAgentConfigChange={(value) => setForm((current) => ({ ...current, voice_agent_config_id: value }))}
          onVoiceModeChange={(value) => setVoiceField('voice_mode', value)}
          onVoiceIdChange={(value) => setVoiceField('voice_id', value)}
          onVoiceTextSettingChange={(key, value) => setVoiceField(key, value)}
          onVoiceSpeakerBoostChange={(value) => setVoiceField('voice_use_speaker_boost', value)}
          onPreviewProviderVoice={handlePreviewProviderVoice}
          onPreviewExternalVoice={handlePreviewExternalVoice}
          t={t}
        />
        {form.management_mode === 'serviglobal_managed' ? (
          <AgentToolsSection
            locale={locale}
            catalog={toolCatalog}
            enabledKeys={form.enabled_tools}
            disabled={!canEdit}
            onToggle={setToolEnabled}
            t={t}
          />
        ) : null}
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
        <div className="flex items-center gap-2">
          {agent.status === 'active' && agent.published_version_id && publishedVersion && providers.some((provider) => provider.status === 'active') ? (
            <AgentVoiceTest
              agentId={agent.id}
              agentName={agent.name}
              published={{
                id: publishedVersion.id,
                version: publishedVersion.version,
                provider: publishedVersion.runtime_binding.realtime.provider,
                runtimeEngine: 'livekit',
                pipelineType: publishedVersion.runtime_binding.pipeline_type,
              }}
            />
          ) : null}
          {canEdit && agent.status === 'active' && agent.published_version_id ? (
            <ActionDialog
              trigger={
                <Button type="button" variant="outline" size="sm" disabled={lifecycleBusy}>
                  {t('actions.unpublish')}
                </Button>
              }
              title={t('confirm.unpublish.title')}
              description={t('confirm.unpublish.description')}
              confirmLabel={t('actions.unpublish')}
              cancelLabel={t('common.cancel')}
              busy={lifecycleBusy}
              onConfirm={handleUnpublish}
            />
          ) : null}
          {editable && !archived ? (
            <ActionDialog
            trigger={
              <Button type="button" variant="ghost" size="sm" disabled={lifecycleBusy}>
                <Archive className="mr-1.5 size-4" aria-hidden="true" />
                {t('actions.archive')}
              </Button>
            }
            title={t('confirm.archive.title')}
            description={t('confirm.archive.description')}
            confirmLabel={t('actions.archive')}
            cancelLabel={t('common.cancel')}
            destructive
            busy={lifecycleBusy}
            onConfirm={handleArchive}
            />
          ) : null}
          {canEdit && archived ? (
            <ActionDialog
              trigger={
                <Button type="button" variant="destructive" size="sm" disabled={lifecycleBusy}>
                  {t('actions.delete')}
                </Button>
              }
              title={t('confirm.delete.title')}
              description={t('confirm.delete.description')}
              confirmLabel={t('confirm.delete.confirmLabel')}
              cancelLabel={t('common.cancel')}
              destructive
              busy={lifecycleBusy}
              onConfirm={handleDelete}
            />
          ) : null}
        </div>
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
            <GeneralFields field={field} disabled={!editable || !hasDraft} providerManaged={form.management_mode === 'provider_managed'} t={t} />
          ) : null}

          {tab === 'behavior' ? (
            <BehaviorFields
              behavior={form.behavior}
              onChange={setBehavior}
              disabled={!editable || !hasDraft}
              t={t}
            />
          ) : null}

          {tab === 'model' ? (
            <AgentModelSection
              pipelineType={form.pipeline_type}
              provider={form.provider}
              model={form.model}
              providers={providers}
              models={models}
              managementMode={form.management_mode}
              providerAgentId={form.provider_agent_id}
              providerAgentName={form.provider_agent_name}
              observedRevisionId={form.observed_published_revision_id}
              currentRevisionId={providerAgents.find((item) => item.agent_id === form.provider_agent_id)?.published_revision_id ?? null}
              hasBlockingTools={providerAgents.find((item) => item.agent_id === form.provider_agent_id)?.has_unsupported_client_tools ?? false}
              modelSettings={form.model_settings}
              disabled={!editable || !hasDraft}
              onManagementModeChange={(value) => {
                setForm((current) => ({ ...current, management_mode: value, model: value === 'provider_managed' ? 'ultravox-v0.7' : 'ultravox' }));
                setSaved(false);
              }}
              onProviderChange={(value) => {
                setForm((current) => ({ ...current, provider: value }));
                setSaved(false);
              }}
              onModelChange={(value) => {
                setForm((current) => ({ ...current, model: value }));
                setSaved(false);
              }}
              onModelSettingTextChange={setModelSettingText}
              onModelSettingBooleanChange={setModelSettingBoolean}
              t={t}
            />
          ) : null}

          {tab === 'voice' ? (
            <VoiceFields
              managementMode={form.management_mode}
              providerVoices={providerVoices}
              voiceAgentConfigId={form.voice_agent_config_id}
              voiceAgents={voiceAgents}
              voiceMode={form.voice_mode}
              voiceId={form.voice_id}
              voiceModel={form.voice_model}
              voiceSpeed={form.voice_speed}
              voiceStability={form.voice_stability}
              voiceSimilarityBoost={form.voice_similarity_boost}
              voiceUseSpeakerBoost={form.voice_use_speaker_boost}
              previewBusy={previewBusy}
              previewedExternalVoice={previewedExternalVoice}
              disabled={!editable || !hasDraft || form.management_mode === 'provider_managed'}
              onVoiceAgentConfigChange={(value) => {
                setForm((current) => ({ ...current, voice_agent_config_id: value }));
                setSaved(false);
              }}
              onVoiceModeChange={(value) => setVoiceField('voice_mode', value)}
              onVoiceIdChange={(value) => setVoiceField('voice_id', value)}
              onVoiceTextSettingChange={(key, value) => setVoiceField(key, value)}
              onVoiceSpeakerBoostChange={(value) => setVoiceField('voice_use_speaker_boost', value)}
              onPreviewProviderVoice={handlePreviewProviderVoice}
              onPreviewExternalVoice={handlePreviewExternalVoice}
              t={t}
            />
          ) : null}

          {tab === 'tools' ? (
            <AgentToolsSection
              locale={locale}
              catalog={toolCatalog}
              enabledKeys={form.enabled_tools}
              disabled={!editable || !hasDraft || form.management_mode === 'provider_managed'}
              onToggle={setToolEnabled}
              t={t}
            />
          ) : null}

          {tab === 'versions' ? (
            <VersionsPanel versions={versions} publishedVersionId={agent.published_version_id} t={t} />
          ) : null}

          {tab !== 'versions' && hasDraft && editable &&
          form.management_mode === 'serviglobal_managed' &&
          form.voice_mode === 'provider_external' &&
          form.voice_id.trim() &&
          !previewedExternalVoice ? (
            <p className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950">
              {t('voice.origin.notTestedWarning')}
            </p>
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
              <Button onClick={handlePublish} disabled={publishing || (form.management_mode === 'serviglobal_managed' && !form.system_prompt.trim())}>
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
  providerManaged,
  t,
}: {
  field: <K extends keyof FormState>(
    key: K
  ) => { value: string; onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => void };
  disabled: boolean;
  providerManaged: boolean;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('tabs.general')}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <AgentFieldLabel label={t('fields.name')} help={t('help.fields.name')} required />
          <input className={FIELD_CLASS} disabled={disabled} {...field('name')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <AgentFieldLabel label={t('fields.description')} help={t('help.fields.description')} />
          <input className={FIELD_CLASS} disabled={disabled} {...field('description')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.language')} help={t('help.fields.language')} required />
          <input className={FIELD_CLASS} disabled={disabled} {...field('language')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.timezone')} help={t('help.fields.timezone')} required />
          <input className={FIELD_CLASS} disabled={disabled} {...field('timezone')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.role')} help={t('help.fields.role')} />
          <input className={FIELD_CLASS} disabled={disabled || providerManaged} {...field('role')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.objective')} help={t('help.fields.objective')} />
          <input className={FIELD_CLASS} disabled={disabled || providerManaged} {...field('objective')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm sm:col-span-2">
          <AgentFieldLabel label={t('fields.systemPrompt')} help={t('help.fields.systemPrompt')} required />
          <textarea className={`${FIELD_CLASS} min-h-32`} disabled={disabled || providerManaged} {...field('system_prompt')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.greeting')} help={t('help.fields.greeting')} />
          <input className={FIELD_CLASS} disabled={disabled || providerManaged} {...field('greeting')} />
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <AgentFieldLabel label={t('fields.closing')} help={t('help.fields.closing')} />
          <input className={FIELD_CLASS} disabled={disabled || providerManaged} {...field('closing')} />
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
          <AgentFieldLabel label={t('fields.responseStyle')} help={t('help.fields.responseStyle')} />
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
          <AgentFieldLabel label={t('fields.interruptions')} help={t('help.fields.interruptions')} />
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
          <AgentFieldLabel label={t('fields.turnDetection')} help={t('help.fields.turnDetection')} />
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
          <AgentFieldLabel label={t('fields.confirmationStrategy')} help={t('help.fields.confirmationStrategy')} />
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
        <div className="flex items-center gap-2 text-sm sm:col-span-2">
          <input
            id="agent-first"
            type="checkbox"
            disabled={disabled}
            checked={behavior.agent_first}
            onChange={(e) => onChange('agent_first', e.target.checked)}
            className="size-4 rounded border-input"
          />
          <label htmlFor="agent-first" className="font-medium text-foreground">{t('fields.agentFirst')}</label>
          <AgentFieldLabel label={t('fields.agentFirst')} help={t('help.fields.agentFirst')} showLabel={false} />
        </div>
      </CardContent>
    </Card>
  );
}

function VoiceFields({
  managementMode,
  providerVoices,
  voiceAgentConfigId,
  voiceAgents,
  voiceMode,
  voiceId,
  voiceModel,
  voiceSpeed,
  voiceStability,
  voiceSimilarityBoost,
  voiceUseSpeakerBoost,
  previewBusy,
  previewedExternalVoice,
  disabled,
  onVoiceAgentConfigChange,
  onVoiceModeChange,
  onVoiceIdChange,
  onVoiceTextSettingChange,
  onVoiceSpeakerBoostChange,
  onPreviewProviderVoice,
  onPreviewExternalVoice,
  t,
}: {
  providerVoices: UltravoxVoiceSummary[];
  voiceAgentConfigId: string;
  voiceAgents: VoiceAgentConfigResponse[];
  managementMode: 'serviglobal_managed' | 'provider_managed';
  voiceMode: 'provider' | 'provider_external';
  voiceId: string;
  voiceModel: string;
  voiceSpeed: string;
  voiceStability: string;
  voiceSimilarityBoost: string;
  voiceUseSpeakerBoost: boolean;
  previewBusy: 'provider' | 'provider_external' | null;
  previewedExternalVoice: boolean;
  disabled: boolean;
  onVoiceAgentConfigChange: (value: string) => void;
  onVoiceModeChange: (value: 'provider' | 'provider_external') => void;
  onVoiceIdChange: (value: string) => void;
  onVoiceTextSettingChange: (
    key: 'voice_model' | 'voice_speed' | 'voice_stability' | 'voice_similarity_boost',
    value: string
  ) => void;
  onVoiceSpeakerBoostChange: (value: boolean) => void;
  onPreviewProviderVoice: () => void;
  onPreviewExternalVoice: () => void;
  t: ReturnType<typeof useTranslations>;
}) {
  return (
    <div className="space-y-4">
      {managementMode === 'serviglobal_managed' ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">{t('voice.origin.title')}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-4">
              <div className="flex items-center gap-2 text-sm">
                <input
                  id="voice-origin-provider"
                  type="radio"
                  name="voice-origin"
                  disabled={disabled}
                  checked={voiceMode === 'provider'}
                  onChange={() => onVoiceModeChange('provider')}
                  className="size-4"
                />
                <label htmlFor="voice-origin-provider" className="font-medium text-foreground">{t('voice.origin.provider')}</label>
                <AgentFieldLabel label={t('voice.origin.provider')} help={t('help.voice.provider')} showLabel={false} />
              </div>
              <div className="flex items-center gap-2 text-sm">
                <input
                  id="voice-origin-external"
                  type="radio"
                  name="voice-origin"
                  disabled={disabled}
                  checked={voiceMode === 'provider_external'}
                  onChange={() => onVoiceModeChange('provider_external')}
                  className="size-4"
                />
                <label htmlFor="voice-origin-external" className="font-medium text-foreground">{t('voice.origin.providerExternal')}</label>
                <AgentFieldLabel label={t('voice.origin.providerExternal')} help={t('help.voice.providerExternal')} showLabel={false} />
              </div>
            </div>

            {voiceMode === 'provider' ? (
              <div className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-end">
                <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.catalogVoice')} help={t('help.voice.catalogVoice')} />
                  <select
                    className={FIELD_CLASS}
                    disabled={disabled || providerVoices.length === 0}
                    value={voiceId}
                    onChange={(e) => onVoiceIdChange(e.target.value)}
                  >
                    <option value="">{providerVoices.length === 0 ? t('voice.origin.noCatalogVoices') : t('voice.linkNone')}</option>
                    {providerVoices.map((v) => (
                      <option key={v.voice_id} value={v.voice_id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </label>
                <Button
                  type="button"
                  variant="outline"
                  disabled={disabled || !voiceId.trim() || previewBusy !== null}
                  onClick={onPreviewProviderVoice}
                >
                  {previewBusy === 'provider' ? (
                    <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Play className="mr-2 size-4" aria-hidden="true" />
                  )}
                  {t('voice.origin.listen')}
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.externalProviderLabel')} help={t('help.voice.externalProviderLabel')} />
                  <input className={FIELD_CLASS} disabled value="ElevenLabs" />
                </label>
                <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.externalVoiceId')} help={t('help.voice.externalVoiceId')} />
                  <input
                    className={FIELD_CLASS}
                    disabled={disabled}
                    value={voiceId}
                    placeholder={t('voice.origin.externalVoiceIdPlaceholder')}
                    onChange={(e) => onVoiceIdChange(e.target.value)}
                  />
                  <span className="text-xs text-muted-foreground">{t('voice.origin.externalVoiceIdHelp')}</span>
                </label>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.externalModel')} help={t('help.voice.externalModel')} />
                    <input
                      className={FIELD_CLASS}
                      disabled={disabled}
                      value={voiceModel}
                      onChange={(e) => onVoiceTextSettingChange('voice_model', e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.speed')} help={t('help.voice.speed')} />
                    <input
                      type="number"
                      step="0.1"
                      min={0.7}
                      max={1.2}
                      className={FIELD_CLASS}
                      disabled={disabled}
                      value={voiceSpeed}
                      onChange={(e) => onVoiceTextSettingChange('voice_speed', e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.stability')} help={t('help.voice.stability')} />
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      max={1}
                      className={FIELD_CLASS}
                      disabled={disabled}
                      value={voiceStability}
                      onChange={(e) => onVoiceTextSettingChange('voice_stability', e.target.value)}
                    />
                  </label>
                  <label className="flex flex-col gap-1.5 text-sm">
                  <AgentFieldLabel label={t('voice.origin.similarityBoost')} help={t('help.voice.similarityBoost')} />
                    <input
                      type="number"
                      step="0.05"
                      min={0}
                      max={1}
                      className={FIELD_CLASS}
                      disabled={disabled}
                      value={voiceSimilarityBoost}
                      onChange={(e) => onVoiceTextSettingChange('voice_similarity_boost', e.target.value)}
                    />
                  </label>
                </div>
                <div className="flex items-center gap-2 text-sm">
                  <input
                    id="voice-speaker-boost"
                    type="checkbox"
                    disabled={disabled}
                    checked={voiceUseSpeakerBoost}
                    onChange={(e) => onVoiceSpeakerBoostChange(e.target.checked)}
                    className="size-4 rounded border-input"
                  />
                  <label htmlFor="voice-speaker-boost" className="font-medium text-foreground">{t('voice.origin.speakerBoost')}</label>
                  <AgentFieldLabel label={t('voice.origin.speakerBoost')} help={t('help.voice.speakerBoost')} showLabel={false} />
                </div>
                <Button
                  type="button"
                  variant="outline"
                  disabled={disabled || !voiceId.trim() || previewBusy !== null}
                  onClick={onPreviewExternalVoice}
                >
                  {previewBusy === 'provider_external' ? (
                    <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Play className="mr-2 size-4" aria-hidden="true" />
                  )}
                  {t('voice.origin.tryVoice')}
                </Button>
                {previewedExternalVoice ? (
                  <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <CheckCircle2 className="size-3.5 text-cyan-500" aria-hidden="true" />
                    {t('voice.origin.tested')}
                  </p>
                ) : null}
              </div>
            )}
          </CardContent>
        </Card>
      ) : null}

      {managementMode === 'serviglobal_managed' ? <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('voice.linkTitle')}</CardTitle>
        </CardHeader>
        <CardContent>
          <label className="flex flex-col gap-1.5 text-sm">
            <AgentFieldLabel label={t('voice.linkLabel')} help={t('help.voice.link')} />
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
      </Card> : null}
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
