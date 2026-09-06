'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Archive,
  ArrowLeft,
  ArrowRight,
  ChevronLeft,
  Eye,
  FileText,
  Lock,
  Mic2,
  PanelLeft,
  RadioTower,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { useTranslations } from 'next-intl';
import {
  archiveVoiceExperienceAction,
  createVoiceExperienceAction,
  deleteVoiceExperienceAction,
  deleteVoiceExperienceVersionAction,
  fetchVoiceContextSchemaAction,
  fetchVoiceExperienceVersionsAction,
  publishVoiceExperienceAction,
  unarchiveVoiceExperienceAction,
  unpublishVoiceExperienceAction,
  updateVoiceExperienceAction,
} from '@/app/[locale]/(tenant)/voice-ai/experiences/actions';
import { ActionDialog } from './ActionDialog';
import { VoiceExperienceStatusBadge } from './VoiceExperienceStatusBadge';
import { ContextSchemaManager } from './context-schemas/ContextSchemaManager';
import { FieldHelp } from '@/components/crm/integrations/FieldHelp';
import { UnsavedChangesGuard } from './editor/UnsavedChangesGuard';
import { VersionHistoryPanel } from './editor/VersionHistoryPanel';
import { VoiceExperiencePreview } from './preview/VoiceExperiencePreview';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  isVoiceExperienceAgentLocked,
  isVoiceExperienceDirty,
} from '@/lib/voice-experiences/change-detection';
import { canDeleteArchivedExperience } from '@/lib/voice-experiences/deletion';
import { getVoiceExperienceMessageKey } from '@/lib/voice-experiences/error-messages';
import {
  createVoiceExperienceDefaults,
  validateVoiceExperience,
  type ValidationErrors,
} from '@/lib/voice-experiences/validation';
import type { VoiceAgentConfigResponse } from '@/types/crm';
import type {
  VoiceContextSchemaResponse,
  VoiceContextSchemaSummaryResponse,
  VoiceExperienceResponse,
  VoiceExperienceVersionResponse,
  VoiceExperienceWriteRequest,
} from '@/types/voice-experiences';

const FIELD_CLASS =
  'min-h-11 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground read-only:bg-muted/60';

const EDITOR_ERROR_PREFIXES = {
  general: ['name', 'default_locale'],
  agentContext: ['agent_config_id', 'context_schema_id'],
  content: ['content.'],
  appearance: ['theme.'],
  consent: ['consent.'],
  behavior: ['call_settings.'],
  versions: [],
} as const;

type Props = {
  mode: 'create' | 'edit';
  locale: string;
  canEdit: boolean;
  agents: VoiceAgentConfigResponse[];
  initialExperience?: VoiceExperienceResponse | null;
  initialVersions?: VoiceExperienceVersionResponse[];
  // true when the version history could not be read; deletion fails closed.
  versionsUnknown?: boolean;
  initialSchemas?: VoiceContextSchemaSummaryResponse[];
  initialSchema?: VoiceContextSchemaResponse | null;
};

type SaveState = 'idle' | 'saving' | 'saved' | 'error';

function toWriteRequest(
  experience: VoiceExperienceResponse | VoiceExperienceVersionResponse
): VoiceExperienceWriteRequest {
  return {
    agent_config_id: experience.agent_config_id,
    context_schema_id: experience.context_schema_id,
    name: experience.name,
    default_locale: experience.default_locale,
    content: experience.content,
    theme: experience.theme,
    consent: experience.consent,
    call_settings: experience.call_settings,
  };
}

export function VoiceExperienceBuilder({
  mode,
  locale,
  canEdit,
  agents,
  initialExperience = null,
  initialVersions = [],
  versionsUnknown = false,
  initialSchemas = [],
  initialSchema = null,
}: Props) {
  const t = useTranslations('crm.voiceExperiences');
  const router = useRouter();
  const initialForm = useMemo(
    () =>
      initialExperience
        ? toWriteRequest(initialExperience)
        : createVoiceExperienceDefaults(locale),
    [initialExperience, locale]
  );
  const [form, setForm] = useState(initialForm);
  const [baseline, setBaseline] = useState(initialForm);
  const [experience, setExperience] = useState(initialExperience);
  const [versions, setVersions] = useState(initialVersions);
  const [schemas, setSchemas] = useState(initialSchemas);
  const [schemaDetail, setSchemaDetail] = useState<VoiceContextSchemaResponse | null>(
    initialSchema
  );
  const [currentStep, setCurrentStep] = useState(0);
  const [editorSection, setEditorSection] = useState(0);
  const [mobileView, setMobileView] = useState<'form' | 'preview'>('form');
  const [errors, setErrors] = useState<ValidationErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<SaveState>('idle');
  const [submitting, setSubmitting] = useState(false);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [selectedVersionSchema, setSelectedVersionSchema] =
    useState<VoiceContextSchemaResponse | null>(null);

  const dirty = isVoiceExperienceDirty(form, baseline);
  const archived = experience?.status === 'archived';
  const editable = canEdit && !archived;
  const agentLocked = isVoiceExperienceAgentLocked(mode, versionsUnknown, versions.length);
  const activeSchema =
    schemaDetail?.id === form.context_schema_id && schemaDetail.status === 'active';
  const canDeleteExperience = experience
    ? canDeleteArchivedExperience(experience.status)
    : false;
  const selectedVersion = versions.find((version) => version.id === selectedVersionId) ?? null;
  const previewForm = selectedVersion ? toWriteRequest(selectedVersion) : form;
  const previewContextFields = selectedVersion
    ? selectedVersionSchema?.fields ?? []
    : schemaDetail?.fields ?? [];
  const publishDisabledReason = !canEdit
    ? t('editor.publishReasons.readOnly')
    : archived
      ? t('editor.publishReasons.archived')
      : dirty
        ? t('editor.publishReasons.unsaved')
        : !activeSchema
          ? t('editor.publishReasons.schemaInactive')
          : null;
  const wizardSteps = [
    'agent',
    'contextSchema',
    'basicInfo',
    'content',
    'appearance',
    'consent',
    'callSettings',
    'preview',
    'create',
  ] as const;
  const editorSections = [
    'general',
    'agentContext',
    'content',
    'appearance',
    'consent',
    'behavior',
    'versions',
  ] as const;

  const updateRoot = <K extends keyof VoiceExperienceWriteRequest>(
    key: K,
    value: VoiceExperienceWriteRequest[K]
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
    setSaveState('idle');
    // Editing must always preview the live draft, never a frozen historical version.
    setSelectedVersionId(null);
    setSelectedVersionSchema(null);
  };

  const validationMessage = (path: string) =>
    errors[path] ? (
      <span className="text-xs text-destructive">{t(`validation.${errors[path]}`)}</span>
    ) : null;

  const validateStep = (step: number) => {
    const all = validateVoiceExperience(form);
    const prefixes: Record<number, string[]> = {
      0: ['agent_config_id'],
      1: ['context_schema_id'],
      2: ['name', 'default_locale'],
      3: ['content.'],
      4: ['theme.'],
      5: ['consent.'],
      6: ['call_settings.'],
      7: [],
      8: [],
    };
    const relevant = Object.fromEntries(
      Object.entries(all).filter(([path]) =>
        prefixes[step]?.some((prefix) => path === prefix || path.startsWith(prefix))
      )
    );
    setErrors(relevant);
    return Object.keys(relevant).length === 0;
  };

  const nextStep = () => {
    if (!validateStep(currentStep)) return;
    setCurrentStep((step) => Math.min(step + 1, wizardSteps.length - 1));
  };

  // Never surface a raw backend detail: unknown 409/422 fall back to localized
  // conflict/validation messages via the shared safe mapper.
  const safeError = (status: number, detail: string) =>
    t(getVoiceExperienceMessageKey(status, detail));

  const save = async () => {
    if (submitting || !editable) return;
    const nextErrors = validateVoiceExperience(form);
    if (Object.keys(nextErrors).length) {
      setErrors(nextErrors);
      setServerError(t('errors.validation'));
      return;
    }
    setSubmitting(true);
    setSaveState('saving');
    setServerError(null);
    const result =
      mode === 'create'
        ? await createVoiceExperienceAction(locale, form)
        : await updateVoiceExperienceAction(locale, experience!.id, form);
    setSubmitting(false);
    if (!result.ok) {
      setSaveState('error');
      setServerError(safeError(result.status, result.detail));
      return;
    }
    setExperience(result.data);
    const nextBaseline = toWriteRequest(result.data);
    setForm(nextBaseline);
    setBaseline(nextBaseline);
    setSaveState('saved');
    if (mode === 'create') {
      router.push(`/${locale}/voice-ai/experiences/${result.data.id}`);
    } else {
      router.refresh();
    }
  };

  const transitionExperience = async (
    action: (
      locale: string,
      id: string
    ) => Promise<
      | { ok: true; data: VoiceExperienceResponse }
      | { ok: false; status: number; detail: string }
    >
  ) => {
    if (!experience || submitting) return;
    setSubmitting(true);
    setServerError(null);
    const result = await action(locale, experience.id);
    setSubmitting(false);
    if (!result.ok) {
      setServerError(safeError(result.status, result.detail));
      return;
    }
    setExperience(result.data);
    if (action === publishVoiceExperienceAction) {
      const history = await fetchVoiceExperienceVersionsAction(experience.id);
      if (history.ok) setVersions(history.data);
    }
    router.refresh();
  };

  const deleteExperience = async () => {
    if (!experience || submitting) return;
    setSubmitting(true);
    setServerError(null);
    const result = await deleteVoiceExperienceAction(locale, experience.id);
    setSubmitting(false);
    if (!result.ok) {
      setServerError(safeError(result.status, result.detail));
      return;
    }
    router.push(`/${locale}/voice-ai/experiences`);
  };

  const selectVersion = async (version: VoiceExperienceVersionResponse) => {
    if (submitting) return;
    if (selectedVersionId === version.id) {
      setSelectedVersionId(null);
      setSelectedVersionSchema(null);
      return;
    }
    setSubmitting(true);
    setServerError(null);
    const schemaResult = await fetchVoiceContextSchemaAction(version.context_schema_id);
    setSubmitting(false);
    if (!schemaResult.ok) {
      setServerError(safeError(schemaResult.status, schemaResult.detail));
      return;
    }
    setSelectedVersionId(version.id);
    setSelectedVersionSchema(schemaResult.data);
  };

  const restoreVersion = async (version: VoiceExperienceVersionResponse) => {
    if (submitting || !editable) return;
    setSubmitting(true);
    setServerError(null);
    const schemaResult =
      selectedVersionId === version.id && selectedVersionSchema
        ? { ok: true as const, data: selectedVersionSchema }
        : await fetchVoiceContextSchemaAction(version.context_schema_id);
    setSubmitting(false);
    if (!schemaResult.ok) {
      setServerError(safeError(schemaResult.status, schemaResult.detail));
      return;
    }
    setForm(toWriteRequest(version));
    setSchemaDetail(schemaResult.data);
    setSelectedVersionId(null);
    setSelectedVersionSchema(null);
    setErrors({});
    setSaveState('idle');
    setEditorSection(0);
  };

  const deleteVersion = async (version: VoiceExperienceVersionResponse) => {
    if (!experience || submitting || !editable) return;
    setSubmitting(true);
    setServerError(null);
    const result = await deleteVoiceExperienceVersionAction(
      locale,
      experience.id,
      version.id
    );
    setSubmitting(false);
    if (!result.ok) {
      setServerError(safeError(result.status, result.detail));
      return;
    }
    setVersions((current) => current.filter((item) => item.id !== version.id));
    if (selectedVersionId === version.id) {
      setSelectedVersionId(null);
      setSelectedVersionSchema(null);
    }
    router.refresh();
  };

  const sectionTitle = mode === 'create'
    ? t(`wizard.steps.${wizardSteps[currentStep]}`)
    : t(`editor.sections.${editorSections[editorSection]}`);

  const sectionHasErrors = (section: (typeof editorSections)[number]) =>
    Object.keys(errors).some((path) =>
      EDITOR_ERROR_PREFIXES[section].some(
        (prefix) => path === prefix || path.startsWith(prefix)
      )
    );

  const renderAgent = () => (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-foreground">{t('form.agent.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.agent.description')}</p>
      </div>
      {agentLocked ? (
        <p className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-800 dark:text-amber-200">
          {t(
            versionsUnknown
              ? 'editor.agentLockedHistoryUnknown'
              : 'editor.agentLockedHasPublished'
          )}
        </p>
      ) : null}
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.agent.label')}
          <FieldHelp label={t('form.agent.label')} required>{t('help.agent')}</FieldHelp>
        </span>
        <select
          className={FIELD_CLASS}
          value={form.agent_config_id}
          disabled={!editable || agentLocked}
          onChange={(event) => {
            updateRoot('agent_config_id', event.target.value);
            updateRoot('context_schema_id', '');
            setSchemaDetail(null);
            setSchemas([]);
          }}
        >
          <option value="">{t('form.agent.placeholder')}</option>
          {agents
            .filter((agent) => agent.status === 'active')
            .map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.display_name}
              </option>
            ))}
        </select>
        {validationMessage('agent_config_id')}
      </label>
    </div>
  );

  const renderContext = () => (
    <div className="space-y-5">
      <div>
        <h3 className="flex items-center gap-1.5 text-lg font-bold text-foreground">
          {t('form.context.title')}
          <FieldHelp label={t('form.context.title')} required>{t('help.contextSchema')}</FieldHelp>
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.context.description')}</p>
      </div>
      {validationMessage('context_schema_id')}
      <ContextSchemaManager
        agentConfigId={form.agent_config_id}
        locale={locale}
        canEdit={editable}
        selectedSchemaId={form.context_schema_id}
        initialSchemas={schemas}
        initialSchema={schemaDetail}
        onSchemasChange={setSchemas}
        onSchemaSelected={(schema) => {
          updateRoot('context_schema_id', schema.id);
          setSchemaDetail(schema);
        }}
        onSchemaDetailChange={setSchemaDetail}
      />
    </div>
  );

  const renderGeneral = () => (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-foreground">{t('form.basic.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.basic.description')}</p>
      </div>
      <div className="grid gap-4 sm:grid-cols-[1fr_160px]">
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.basic.name')}
            <FieldHelp label={t('form.basic.name')} required>{t('help.basic.name')}</FieldHelp>
          </span>
          <input
            className={FIELD_CLASS}
            value={form.name}
            maxLength={160}
            disabled={!editable}
            onChange={(event) => updateRoot('name', event.target.value)}
          />
          <span className="flex justify-between gap-2">
            {validationMessage('name')}
            <span className="ml-auto text-xs font-normal text-muted-foreground">{form.name.length}/160</span>
          </span>
        </label>
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.basic.locale')}
            <FieldHelp align="right" label={t('form.basic.locale')} required>{t('help.basic.locale')}</FieldHelp>
          </span>
          <select
            className={FIELD_CLASS}
            value={form.default_locale}
            disabled={!editable}
            onChange={(event) => updateRoot('default_locale', event.target.value)}
          >
            <option value="es">ES</option>
            <option value="en">EN</option>
          </select>
          {validationMessage('default_locale')}
        </label>
      </div>
    </div>
  );

  const renderContent = () => {
    const fields: Array<[keyof VoiceExperienceWriteRequest['content'], number]> = [
      ['title', 160],
      ['description', 2000],
      ['submit_label', 80],
      ['call_label', 80],
      ['success_message', 1000],
    ];
    return (
      <div className="space-y-5">
        <div>
          <h3 className="text-lg font-bold text-foreground">{t('form.content.title')}</h3>
          <p className="mt-1 text-sm text-muted-foreground">{t('form.content.description')}</p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          {fields.map(([key, max], index) => (
            <label
              key={key}
              className={`grid gap-2 text-sm font-semibold text-foreground ${
                index === 1 || index === 4 ? 'sm:col-span-2' : ''
              }`}
            >
              <span className="flex items-center gap-1.5">
                {t(`form.content.fields.${key}`)}
                <FieldHelp
                  align={index % 2 ? 'right' : 'left'}
                  label={t(`form.content.fields.${key}`)}
                  required
                >
                  {t(`help.content.${key}`)}
                </FieldHelp>
              </span>
              {index === 1 || index === 4 ? (
                <textarea
                  className={FIELD_CLASS}
                  rows={index === 1 ? 4 : 3}
                  maxLength={max}
                  disabled={!editable}
                  value={form.content[key]}
                  onChange={(event) =>
                    updateRoot('content', { ...form.content, [key]: event.target.value })
                  }
                />
              ) : (
                <input
                  className={FIELD_CLASS}
                  maxLength={max}
                  disabled={!editable}
                  value={form.content[key]}
                  onChange={(event) =>
                    updateRoot('content', { ...form.content, [key]: event.target.value })
                  }
                />
              )}
              <span className="flex justify-between gap-2">
                {validationMessage(`content.${key}`)}
                <span className="ml-auto text-xs font-normal text-muted-foreground">
                  {form.content[key].length}/{max}
                </span>
              </span>
            </label>
          ))}
        </div>
      </div>
    );
  };

  const renderAppearance = () => (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-foreground">{t('form.appearance.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.appearance.description')}</p>
      </div>
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.appearance.logoUrl')}
          <FieldHelp label={t('form.appearance.logoUrl')} required={false}>{t('help.appearance.logoUrl')}</FieldHelp>
        </span>
        <input
          type="url"
          className={FIELD_CLASS}
          value={form.theme.logo_url ?? ''}
          disabled={!editable}
          placeholder="https://"
          onChange={(event) =>
            updateRoot('theme', { ...form.theme, logo_url: event.target.value || null })
          }
        />
        {validationMessage('theme.logo_url')}
      </label>
      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-end">
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.appearance.color')}
            <FieldHelp label={t('form.appearance.color')} required={false}>{t('help.appearance.color')}</FieldHelp>
          </span>
          <input
            type="color"
            className="h-11 w-20 cursor-pointer rounded-md border border-input bg-background p-1 disabled:cursor-not-allowed"
            value={form.theme.primary_color ?? '#0891B2'}
            disabled={!editable}
            onChange={(event) =>
              updateRoot('theme', { ...form.theme, primary_color: event.target.value })
            }
          />
        </label>
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.appearance.colorHex')}
            <FieldHelp align="right" label={t('form.appearance.colorHex')} required={false}>{t('help.appearance.colorHex')}</FieldHelp>
          </span>
          <input
            className={FIELD_CLASS}
            value={form.theme.primary_color ?? ''}
            disabled={!editable}
            placeholder="#0891B2"
            onChange={(event) =>
              updateRoot('theme', { ...form.theme, primary_color: event.target.value || null })
            }
          />
          {validationMessage('theme.primary_color')}
        </label>
      </div>
      <div className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-end">
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.appearance.backgroundColor')}
            <FieldHelp label={t('form.appearance.backgroundColor')} required={false}>{t('help.appearance.backgroundColor')}</FieldHelp>
          </span>
          <input
            type="color"
            className="h-11 w-20 cursor-pointer rounded-md border border-input bg-background p-1 disabled:cursor-not-allowed"
            value={form.theme.background_color ?? '#F4F7F6'}
            disabled={!editable}
            onChange={(event) =>
              updateRoot('theme', { ...form.theme, background_color: event.target.value })
            }
          />
        </label>
        <label className="grid gap-2 text-sm font-semibold text-foreground">
          <span className="flex items-center gap-1.5">
            {t('form.appearance.backgroundColorHex')}
            <FieldHelp align="right" label={t('form.appearance.backgroundColorHex')} required={false}>{t('help.appearance.backgroundColorHex')}</FieldHelp>
          </span>
          <input
            className={FIELD_CLASS}
            value={form.theme.background_color ?? ''}
            disabled={!editable}
            placeholder="#F4F7F6"
            onChange={(event) =>
              updateRoot('theme', { ...form.theme, background_color: event.target.value || null })
            }
          />
          {validationMessage('theme.background_color')}
        </label>
      </div>
      <fieldset disabled={!editable}>
        <legend className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          {t('form.appearance.colorScheme')}
          <FieldHelp label={t('form.appearance.colorScheme')} required={false}>{t('help.appearance.colorScheme')}</FieldHelp>
        </legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {(['light', 'dark'] as const).map((scheme) => (
            <label
              key={scheme}
              className={`cursor-pointer rounded-lg border p-4 text-sm transition ${
                form.theme.color_scheme === scheme
                  ? 'border-primary/60 bg-primary/[0.06] text-foreground'
                  : 'border-border text-muted-foreground hover:border-primary/30'
              }`}
            >
              <input
                type="radio"
                name="colorScheme"
                value={scheme}
                checked={form.theme.color_scheme === scheme}
                onChange={() => updateRoot('theme', { ...form.theme, color_scheme: scheme })}
                className="sr-only"
              />
              <span className="font-semibold">{t(`form.appearance.colorSchemes.${scheme}`)}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <fieldset disabled={!editable}>
        <legend className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          {t('form.appearance.layout')}
          <FieldHelp label={t('form.appearance.layout')} required>{t('help.appearance.layout')}</FieldHelp>
        </legend>
        <div className="mt-3 grid gap-3 sm:grid-cols-3">
          {(['centered', 'split', 'card'] as const).map((layout) => (
            <label
              key={layout}
              className={`cursor-pointer rounded-lg border p-4 text-sm transition ${
                form.theme.layout === layout
                  ? 'border-primary/60 bg-primary/[0.06] text-foreground'
                  : 'border-border text-muted-foreground hover:border-primary/30'
              }`}
            >
              <input
                type="radio"
                name="layout"
                value={layout}
                checked={form.theme.layout === layout}
                onChange={() => updateRoot('theme', { ...form.theme, layout })}
                className="sr-only"
              />
              <span className="font-semibold">{t(`form.appearance.layouts.${layout}`)}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );

  const renderConsent = () => (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-foreground">{t('form.consent.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.consent.description')}</p>
      </div>
      <label className="flex items-start gap-3 rounded-lg border border-border bg-muted/20 p-4 text-sm text-foreground">
        <input
          type="checkbox"
          className="mt-0.5 size-4"
          checked={form.consent.required}
          disabled={!editable}
          onChange={(event) =>
            updateRoot('consent', { ...form.consent, required: event.target.checked })
          }
        />
        <span>
          <span className="flex items-center gap-1.5 font-semibold">
            {t('form.consent.required')}
            <FieldHelp label={t('form.consent.required')} required={false}>{t('help.consent.required')}</FieldHelp>
          </span>
          <span className="mt-1 block text-xs text-muted-foreground">{t('form.consent.requiredHint')}</span>
        </span>
      </label>
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.consent.label')}
          <FieldHelp label={t('form.consent.label')} required={form.consent.required}>{t('help.consent.label')}</FieldHelp>
        </span>
        <textarea
          className={FIELD_CLASS}
          rows={3}
          maxLength={1000}
          value={form.consent.label ?? ''}
          disabled={!editable}
          onChange={(event) =>
            updateRoot('consent', { ...form.consent, label: event.target.value || null })
          }
        />
        {validationMessage('consent.label')}
      </label>
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.consent.privacyUrl')}
          <FieldHelp label={t('form.consent.privacyUrl')} required={false}>{t('help.consent.privacyUrl')}</FieldHelp>
        </span>
        <input
          type="url"
          className={FIELD_CLASS}
          value={form.consent.privacy_url ?? ''}
          disabled={!editable}
          placeholder="https://"
          onChange={(event) =>
            updateRoot('consent', { ...form.consent, privacy_url: event.target.value || null })
          }
        />
        {validationMessage('consent.privacy_url')}
      </label>
    </div>
  );

  const renderBehavior = () => (
    <div className="space-y-5">
      <div>
        <h3 className="text-lg font-bold text-foreground">{t('form.behavior.title')}</h3>
        <p className="mt-1 text-sm text-muted-foreground">{t('form.behavior.description')}</p>
      </div>
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.behavior.mode')}
          <FieldHelp label={t('form.behavior.mode')} required>{t('help.behavior.mode')}</FieldHelp>
        </span>
        <select
          className={FIELD_CLASS}
          value={form.call_settings.mode}
          disabled={!editable}
          onChange={(event) => updateRoot('call_settings', {
            ...form.call_settings,
            mode: event.target.value as 'webrtc' | 'callback' | 'both',
            phone_field_key: event.target.value === 'webrtc'
              ? null
              : form.call_settings.phone_field_key,
          })}
        >
          <option value="webrtc">{t('form.behavior.modes.webrtc')}</option>
          <option value="callback">{t('form.behavior.modes.callback')}</option>
          <option value="both">{t('form.behavior.modes.both')}</option>
        </select>
      </label>
      {form.call_settings.mode === 'callback' || form.call_settings.mode === 'both' ? (
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="grid gap-2 text-sm font-semibold text-foreground">
            <span className="flex items-center gap-1.5">
              {t('form.behavior.phoneField')}
              <FieldHelp label={t('form.behavior.phoneField')} required>{t('help.behavior.phoneField')}</FieldHelp>
            </span>
            <select
              className={FIELD_CLASS}
              value={form.call_settings.phone_field_key ?? ''}
              disabled={!editable}
              onChange={(event) => updateRoot('call_settings', {
                ...form.call_settings,
                phone_field_key: event.target.value || null,
              })}
            >
              <option value="">{t('form.behavior.phoneFieldPlaceholder')}</option>
              {(schemaDetail?.fields ?? [])
                .filter((field) => field.field_type === 'phone' && field.required && field.collection_mode !== 'internal_only')
                .map((field) => <option key={field.id} value={field.key}>{field.label}</option>)}
            </select>
            {validationMessage('call_settings.phone_field_key')}
          </label>
          <label className="grid gap-2 text-sm font-semibold text-foreground">
            <span className="flex items-center gap-1.5">
              {t('form.behavior.defaultCountry')}
              <FieldHelp label={t('form.behavior.defaultCountry')} required>{t('help.behavior.defaultCountry')}</FieldHelp>
            </span>
            <select
              className={FIELD_CLASS}
              value={form.call_settings.default_country}
              disabled={!editable}
              onChange={(event) => updateRoot('call_settings', {
                ...form.call_settings,
                default_country: event.target.value as VoiceExperienceWriteRequest['call_settings']['default_country'],
              })}
            >
              {(['CO', 'MX', 'AR', 'PA', 'CL', 'EC', 'PE', 'US'] as const).map((country) => (
                <option key={country} value={country}>{t(`form.behavior.countries.${country}`)}</option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      <label className="grid gap-2 text-sm font-semibold text-foreground">
        <span className="flex items-center gap-1.5">
          {t('form.behavior.language')}
          <FieldHelp label={t('form.behavior.language')} required>{t('help.behavior.language')}</FieldHelp>
        </span>
        <select
          className={FIELD_CLASS}
          value={form.call_settings.language}
          disabled={!editable}
          onChange={(event) =>
            updateRoot('call_settings', { ...form.call_settings, language: event.target.value })
          }
        >
          <option value="es">{t('form.behavior.languages.es')}</option>
          <option value="en">{t('form.behavior.languages.en')}</option>
          <option value="es-CO">ES-CO</option>
          <option value="en-US">EN-US</option>
        </select>
        {validationMessage('call_settings.language')}
      </label>
      {form.call_settings.mode === 'webrtc' || form.call_settings.mode === 'both' ? <div className="grid gap-3 sm:grid-cols-2">
        {(['auto_start', 'show_microphone_help'] as const).map((key) => (
          <label key={key} className="flex items-start gap-3 rounded-lg border border-border p-4 text-sm text-foreground">
            <input
              type="checkbox"
              className="mt-0.5 size-4"
              checked={form.call_settings[key]}
              disabled={!editable}
              onChange={(event) =>
                updateRoot('call_settings', { ...form.call_settings, [key]: event.target.checked })
              }
            />
            <span>
              <span className="flex items-center gap-1.5 font-semibold">
                {t(`form.behavior.${key}`)}
                <FieldHelp label={t(`form.behavior.${key}`)} required={false}>
                  {t(`help.behavior.${key}`)}
                </FieldHelp>
              </span>
              <span className="mt-1 block text-xs text-muted-foreground">
                {t(`form.behavior.${key}Hint`)}
              </span>
            </span>
          </label>
        ))}
      </div> : null}
    </div>
  );

  const renderCurrent = () => {
    const index = mode === 'create' ? currentStep : editorSection;
    if (mode === 'create') {
      if (index === 0) return renderAgent();
      if (index === 1) return renderContext();
      if (index === 2) return renderGeneral();
      if (index === 3) return renderContent();
      if (index === 4) return renderAppearance();
      if (index === 5) return renderConsent();
      if (index === 6) return renderBehavior();
      if (index === 7) {
        return (
          <div className="space-y-4">
            <h3 className="text-lg font-bold text-foreground">{t('preview.label')}</h3>
            <VoiceExperiencePreview form={form} contextFields={schemaDetail?.fields ?? []} locale={locale} />
          </div>
        );
      }
      return (
        <div className="space-y-5 text-center">
          <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <ShieldCheck className="size-6" aria-hidden="true" />
          </span>
          <div>
            <h3 className="text-xl font-bold text-foreground">{t('wizard.ready.title')}</h3>
            <p className="mt-2 text-sm text-muted-foreground">{t('wizard.ready.description')}</p>
          </div>
          <dl className="mx-auto grid max-w-lg gap-3 text-left sm:grid-cols-2">
            <div className="rounded-lg bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">{t('form.basic.name')}</dt>
              <dd className="mt-1 text-sm font-semibold">{form.name}</dd>
            </div>
            <div className="rounded-lg bg-muted/40 p-3">
              <dt className="text-xs text-muted-foreground">{t('form.basic.locale')}</dt>
              <dd className="mt-1 text-sm font-semibold uppercase">{form.default_locale}</dd>
            </div>
          </dl>
          <Button type="button" size="lg" disabled={submitting || !canEdit || !form.context_schema_id} onClick={save}>
            {submitting ? <CircularLoader size="xs" glow={false} className="mr-2" /> : <Sparkles className="mr-2 size-4" aria-hidden="true" />}
            {t('wizard.createDraft')}
          </Button>
          {form.context_schema_id && !activeSchema ? (
            <p className="text-sm text-amber-700 dark:text-amber-300">{t('errors.schemaMustBeActiveToPublish')}</p>
          ) : null}
        </div>
      );
    }
    if (index === 0) return renderGeneral();
    if (index === 1) return <div className="space-y-8">{renderAgent()}{renderContext()}</div>;
    if (index === 2) return renderContent();
    if (index === 3) return renderAppearance();
    if (index === 4) return renderConsent();
    if (index === 5) return renderBehavior();
    return (
      <VersionHistoryPanel
        versions={versions}
        publishedVersionId={experience?.published_version_id ?? null}
        locale={locale}
        canEdit={editable}
        busy={submitting}
        selectedVersionId={selectedVersionId}
        onSelect={selectVersion}
        onRestore={restoreVersion}
        onDelete={deleteVersion}
      />
    );
  };

  return (
    <div className="space-y-5">
      <UnsavedChangesGuard dirty={dirty} message={t('editor.unsavedChanges')} />
      <header className="rounded-xl border border-border bg-card p-4 shadow-sm sm:p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <Button asChild variant="ghost" size="icon">
              <Link href={`/${locale}/voice-ai/experiences`} aria-label={t('common.back')}>
                <ArrowLeft className="size-4" aria-hidden="true" />
              </Link>
            </Button>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="truncate text-xl font-bold text-foreground sm:text-2xl">
                  {mode === 'create' ? t('wizard.title') : experience?.name}
                </h1>
                {experience ? <VoiceExperienceStatusBadge status={experience.status} /> : null}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {mode === 'create' ? t('wizard.description') : t('editor.description')}
              </p>
              <p className="mt-2 flex items-start gap-2 text-xs leading-5 text-muted-foreground">
                <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
                {t('list.privateNotice')}
              </p>
              {experience?.status === 'published' && dirty ? (
                <p className="mt-2 text-xs font-medium text-amber-700 dark:text-amber-300">
                  {t('editor.publishedDraftWarning')}
                </p>
              ) : null}
            </div>
          </div>
          {mode === 'edit' ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="mr-1 text-xs text-muted-foreground" aria-live="polite">
                {saveState === 'saving' ? t('common.saving') : saveState === 'saved' ? t('common.saved') : null}
              </span>
              {editable ? (
                <Button type="button" variant="outline" disabled={!dirty || submitting} onClick={save}>
                  {submitting ? <CircularLoader size="xs" glow={false} className="mr-2" /> : <Save className="mr-2 size-4" aria-hidden="true" />}
                  {t('common.save')}
                </Button>
              ) : null}
              {canEdit && experience?.status === 'published' ? (
                <ActionDialog
                  trigger={<Button type="button" disabled={submitting}>{t('actions.unpublish')}</Button>}
                  title={t('confirm.unpublish.title')}
                  description={t('confirm.unpublish.description')}
                  confirmLabel={t('actions.unpublish')}
                  cancelLabel={t('common.cancel')}
                  busy={submitting}
                  onConfirm={() => transitionExperience(unpublishVoiceExperienceAction)}
                />
              ) : null}
              {canEdit && (experience?.status === 'draft' || experience?.status === 'unpublished') ? (
                <div className="flex flex-col items-end gap-1">
                  {activeSchema ? (
                    <ActionDialog
                      trigger={
                        <Button
                          type="button"
                          disabled={submitting || dirty}
                          title={publishDisabledReason ?? undefined}
                        >
                          <RadioTower className="mr-2 size-4" aria-hidden="true" />
                          {t('actions.publish')}
                        </Button>
                      }
                      title={t('confirm.publish.title')}
                      description={t('confirm.publish.description')}
                      confirmLabel={t('actions.publish')}
                      cancelLabel={t('common.cancel')}
                      busy={submitting}
                      onConfirm={() => transitionExperience(publishVoiceExperienceAction)}
                    />
                  ) : (
                      <Button
                        type="button"
                        disabled={submitting || dirty}
                        title={publishDisabledReason ?? undefined}
                        onClick={() => setEditorSection(1)}
                      >
                        <RadioTower className="mr-2 size-4" aria-hidden="true" />
                        {t('actions.publish')}
                      </Button>
                  )}
                  {publishDisabledReason ? (
                    <p className="max-w-56 text-right text-xs text-muted-foreground">
                      {publishDisabledReason}
                    </p>
                  ) : null}
                </div>
              ) : null}
              {canEdit && experience && experience.status !== 'published' && experience.status !== 'archived' ? (
                <ActionDialog
                  trigger={
                    <Button type="button" variant="ghost" size="icon" disabled={submitting} aria-label={t('actions.archive')}>
                      <Archive className="size-4" aria-hidden="true" />
                    </Button>
                  }
                  title={t('confirm.archive.title')}
                  description={t('confirm.archive.description')}
                  confirmLabel={t('actions.archive')}
                  cancelLabel={t('common.cancel')}
                  destructive
                  busy={submitting}
                  onConfirm={() => transitionExperience(archiveVoiceExperienceAction)}
                />
              ) : null}
              {canEdit && experience?.status === 'archived' ? (
                <ActionDialog
                  trigger={
                    <Button type="button" variant="outline" size="sm" disabled={submitting}>
                      <RotateCcw className="mr-2 size-4" aria-hidden="true" />
                      {t('actions.unarchive')}
                    </Button>
                  }
                  title={t('confirm.unarchive.title')}
                  description={t('confirm.unarchive.description')}
                  confirmLabel={t('actions.unarchive')}
                  cancelLabel={t('common.cancel')}
                  busy={submitting}
                  onConfirm={() => transitionExperience(unarchiveVoiceExperienceAction)}
                />
              ) : null}
              {canEdit && canDeleteExperience ? (
                <ActionDialog
                  trigger={
                    <Button type="button" variant="ghost" size="icon" disabled={submitting} aria-label={t('actions.delete')}>
                      <Trash2 className="size-4" aria-hidden="true" />
                    </Button>
                  }
                  title={t('confirm.delete.title')}
                  description={t('confirm.delete.description')}
                  confirmLabel={t('confirm.delete.confirmLabel')}
                  cancelLabel={t('common.cancel')}
                  destructive
                  busy={submitting}
                  onConfirm={deleteExperience}
                />
              ) : null}
            </div>
          ) : null}
        </div>
      </header>

      {serverError ? (
        <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          {serverError}
        </p>
      ) : null}
      {archived ? (
        <p className="rounded-lg border border-zinc-500/20 bg-zinc-500/10 p-4 text-sm text-zinc-700 dark:text-zinc-200">
          {t('editor.readOnlyArchived')}
        </p>
      ) : !canEdit ? (
        <p className="rounded-lg border border-blue-500/20 bg-blue-500/10 p-4 text-sm text-blue-800 dark:text-blue-200">
          {t('editor.readOnlyRole')}
        </p>
      ) : null}

      {mode === 'create' ? (
        <nav aria-label={t('wizard.progress')} className="overflow-x-auto rounded-xl border border-border bg-card p-3">
          <ol className="flex min-w-max items-center gap-1">
            {wizardSteps.map((step, index) => (
              <li key={step}>
                <button
                  type="button"
                  onClick={() => index <= currentStep && setCurrentStep(index)}
                  disabled={index > currentStep}
                  aria-current={index === currentStep ? 'step' : undefined}
                  className={`flex min-h-10 items-center gap-2 rounded-md px-3 text-xs font-semibold transition ${
                    index === currentStep
                      ? 'bg-primary text-primary-foreground'
                      : index < currentStep
                        ? 'bg-primary/10 text-primary'
                        : 'text-muted-foreground'
                  }`}
                >
                  <span className="font-mono">{String(index + 1).padStart(2, '0')}</span>
                  {t(`wizard.steps.${step}`)}
                </button>
              </li>
            ))}
          </ol>
        </nav>
      ) : (
        <nav aria-label={t('editor.navigation')} className="overflow-x-auto border-b border-border">
          <div role="tablist" className="flex min-w-max gap-5">
            {editorSections.map((section, index) => {
              const hasErrors = sectionHasErrors(section);
              return (
                <button
                  key={section}
                  id={`voice-experience-tab-${section}`}
                  type="button"
                  role="tab"
                  aria-controls={`voice-experience-panel-${section}`}
                  aria-selected={editorSection === index}
                  data-invalid={hasErrors || undefined}
                  onClick={() => setEditorSection(index)}
                  className={`flex min-h-11 items-center gap-2 border-b-2 px-1 text-sm font-semibold transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                    editorSection === index
                      ? 'border-primary text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {t(`editor.sections.${section}`)}
                  {hasErrors ? (
                    <span
                      className="size-2 rounded-full bg-destructive"
                      aria-label={t('editor.sectionHasErrors')}
                    />
                  ) : null}
                </button>
              );
            })}
          </div>
        </nav>
      )}

      <div className="flex gap-2 lg:hidden" role="tablist" aria-label={t('editor.mobileView')}>
        <Button
          type="button"
          variant={mobileView === 'form' ? 'default' : 'outline'}
          className="flex-1"
          onClick={() => setMobileView('form')}
        >
          <PanelLeft className="mr-2 size-4" aria-hidden="true" />
          {t('editor.configuration')}
        </Button>
        <Button
          type="button"
          variant={mobileView === 'preview' ? 'default' : 'outline'}
          className="flex-1"
          onClick={() => setMobileView('preview')}
        >
          <Eye className="mr-2 size-4" aria-hidden="true" />
          {t('preview.label')}
        </Button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.08fr)_minmax(340px,0.72fr)]">
        <Card className={mobileView === 'preview' ? 'hidden lg:block' : ''}>
          <CardHeader className="border-b border-border bg-muted/15">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="size-4 text-primary" aria-hidden="true" />
              {sectionTitle}
            </CardTitle>
          </CardHeader>
          <CardContent
            className="p-5 sm:p-6"
            role={mode === 'edit' ? 'tabpanel' : undefined}
            id={mode === 'edit' ? `voice-experience-panel-${editorSections[editorSection]}` : undefined}
            aria-labelledby={mode === 'edit' ? `voice-experience-tab-${editorSections[editorSection]}` : undefined}
          >
            {renderCurrent()}
          </CardContent>
          {mode === 'create' && currentStep < 8 ? (
            <div className="flex items-center justify-between gap-3 border-t border-border p-4 sm:px-6">
              <Button
                type="button"
                variant="ghost"
                disabled={currentStep === 0}
                onClick={() => setCurrentStep((step) => Math.max(0, step - 1))}
              >
                <ChevronLeft className="mr-1.5 size-4" aria-hidden="true" />
                {t('wizard.back')}
              </Button>
              <Button type="button" onClick={nextStep}>
                {t('wizard.next')}
                <ArrowRight className="ml-1.5 size-4" aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </Card>

        <aside className={`min-w-0 lg:sticky lg:top-5 lg:self-start ${mobileView === 'form' ? 'hidden lg:block' : ''}`}>
          {selectedVersion ? (
            <p className="mb-3 rounded-lg border border-cyan-500/25 bg-cyan-500/[0.07] px-3 py-2 text-xs font-semibold text-cyan-800 dark:text-cyan-200">
              {t('versions.previewing', { version: selectedVersion.version })}
            </p>
          ) : null}
          <VoiceExperiencePreview
            form={previewForm}
            contextFields={previewContextFields}
            locale={locale}
          />
          <p className="mt-3 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <Mic2 className="size-3.5" aria-hidden="true" />
            {t('preview.safeNote')}
          </p>
        </aside>
      </div>
    </div>
  );
}
