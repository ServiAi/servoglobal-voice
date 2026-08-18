'use client';

import { useEffect, useRef, useState, useTransition } from 'react';
import {
  Archive,
  Check,
  ChevronRight,
  CopyPlus,
  FileKey2,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getVoiceExperienceMessageKey } from '@/lib/voice-experiences/error-messages';
import {
  activateVoiceContextSchemaAction,
  addVoiceContextFieldAction,
  archiveVoiceContextSchemaAction,
  createVoiceContextSchemaAction,
  deleteVoiceContextFieldAction,
  deleteVoiceContextSchemaAction,
  fetchVoiceContextSchemaAction,
  fetchVoiceContextSchemasAction,
  fetchVoiceContextSchemaVersionsAction,
  forkVoiceContextSchemaVersionAction,
  updateVoiceContextFieldAction,
  updateVoiceContextSchemaMetaAction,
} from '@/app/[locale]/crm/settings/voice-experiences/actions';
import { ActionDialog } from '@/components/crm/voice-experiences/ActionDialog';
import { ContextFieldForm } from './ContextFieldForm';
import { FieldHelp } from '@/components/crm/integrations/FieldHelp';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type {
  VoiceContextFieldRequest,
  VoiceContextFieldResponse,
  VoiceContextSchemaResponse,
  VoiceContextSchemaSummaryResponse,
} from '@/types/voice-experiences';

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

function toSummary(schema: VoiceContextSchemaResponse): VoiceContextSchemaSummaryResponse {
  return {
    id: schema.id,
    agent_config_id: schema.agent_config_id,
    schema_key: schema.schema_key,
    version: schema.version,
    status: schema.status,
    name: schema.name,
    field_count: schema.fields.length,
    updated_at: schema.updated_at,
  };
}

type Props = {
  agentConfigId: string;
  locale: string;
  canEdit: boolean;
  selectedSchemaId: string;
  initialSchemas?: VoiceContextSchemaSummaryResponse[];
  initialSchema?: VoiceContextSchemaResponse | null;
  onSchemasChange?: (schemas: VoiceContextSchemaSummaryResponse[]) => void;
  onSchemaSelected: (schema: VoiceContextSchemaResponse) => void;
  onSchemaDetailChange: (schema: VoiceContextSchemaResponse | null) => void;
};

export function ContextSchemaManager({
  agentConfigId,
  locale,
  canEdit,
  selectedSchemaId,
  initialSchemas = [],
  initialSchema = null,
  onSchemasChange,
  onSchemaSelected,
  onSchemaDetailChange,
}: Props) {
  const t = useTranslations('crm.voiceExperiences');
  const [schemas, setSchemas] = useState(initialSchemas);
  const [detail, setDetail] = useState<VoiceContextSchemaResponse | null>(initialSchema);
  const [versions, setVersions] = useState<VoiceContextSchemaSummaryResponse[]>([]);
  const [loadedAgentId, setLoadedAgentId] = useState(initialSchemas.length ? agentConfigId : '');
  const [showCreate, setShowCreate] = useState(false);
  const [newSchema, setNewSchema] = useState({ schema_key: '', name: '', description: '' });
  const [editingField, setEditingField] = useState<VoiceContextFieldResponse | null>(null);
  const [showFieldForm, setShowFieldForm] = useState(false);
  const [meta, setMeta] = useState({ name: initialSchema?.name ?? '', description: initialSchema?.description ?? '' });
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(null);
  const [isPending, startTransition] = useTransition();
  const latestSchemaRequestId = useRef<string | null>(null);

  const showResultError = (status: number, detailText: string) => {
    // Map known errors and fall back to a localized message; never surface a raw
    // backend detail to the user.
    setMessage({ type: 'error', text: t(getVoiceExperienceMessageKey(status, detailText)) });
  };

  const refreshSchemas = async (agentId = agentConfigId) => {
    if (!agentId) {
      setSchemas([]);
      setDetail(null);
      onSchemaDetailChange(null);
      return;
    }
    const result = await fetchVoiceContextSchemasAction(agentId);
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    setSchemas(result.data);
    onSchemasChange?.(result.data);
    setLoadedAgentId(agentId);
  };

  const loadSchema = async (summary: VoiceContextSchemaSummaryResponse) => {
    latestSchemaRequestId.current = summary.id;
    const [detailResult, versionsResult] = await Promise.all([
      fetchVoiceContextSchemaAction(summary.id),
      fetchVoiceContextSchemaVersionsAction(summary.agent_config_id, summary.schema_key),
    ]);
    if (latestSchemaRequestId.current !== summary.id) return;
    if (!detailResult.ok) {
      showResultError(detailResult.status, detailResult.detail);
      return;
    }
    setDetail(detailResult.data);
    setMeta({ name: detailResult.data.name, description: detailResult.data.description ?? '' });
    onSchemaDetailChange(detailResult.data);
    if (versionsResult.ok) setVersions(versionsResult.data);
  };

  useEffect(() => {
    if (!agentConfigId) {
      latestSchemaRequestId.current = null;
      setSchemas([]);
      setDetail(null);
      setLoadedAgentId('');
      onSchemaDetailChange(null);
      return;
    }
    if (loadedAgentId === agentConfigId) return;
    latestSchemaRequestId.current = null;
    setLoadedAgentId(agentConfigId);
    setSchemas([]);
    setDetail(null);
    setVersions([]);
    onSchemaDetailChange(null);
    startTransition(() => {
      void refreshSchemas(agentConfigId);
    });
    // Server action helpers and parent callbacks are intentionally read from the current render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [agentConfigId, loadedAgentId]);

  useEffect(() => {
    if (!selectedSchemaId || detail?.id === selectedSchemaId) return;
    const summary = schemas.find((item) => item.id === selectedSchemaId);
    if (summary) {
      startTransition(() => {
        void loadSchema(summary);
      });
    } else {
      latestSchemaRequestId.current = selectedSchemaId;
      startTransition(async () => {
        const result = await fetchVoiceContextSchemaAction(selectedSchemaId);
        if (result.ok && latestSchemaRequestId.current === selectedSchemaId) {
          setDetail(result.data);
          setMeta({ name: result.data.name, description: result.data.description ?? '' });
          onSchemaDetailChange(result.data);
        }
      });
    }
    // Loading is keyed only by the selected schema identity and the current local collection.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [detail?.id, schemas, selectedSchemaId]);

  const createSchema = async () => {
    const result = await createVoiceContextSchemaAction(locale, agentConfigId, {
      schema_key: newSchema.schema_key.trim(),
      name: newSchema.name.trim(),
      description: newSchema.description.trim() || null,
    });
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    const summary = toSummary(result.data);
    setSchemas((current) => {
      const next = [summary, ...current];
      onSchemasChange?.(next);
      return next;
    });
    setDetail(result.data);
    setMeta({ name: result.data.name, description: result.data.description ?? '' });
    setShowCreate(false);
    setNewSchema({ schema_key: '', name: '', description: '' });
    onSchemaDetailChange(result.data);
    setMessage({ type: 'success', text: t('contextSchemas.created') });
  };

  const updateMeta = async () => {
    if (!detail) return;
    const result = await updateVoiceContextSchemaMetaAction(locale, detail.id, {
      name: meta.name.trim(),
      description: meta.description.trim() || null,
    });
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    setDetail(result.data);
    onSchemaDetailChange(result.data);
    setSchemas((current) => {
      const next = current.map((item) =>
        item.id === result.data.id ? toSummary(result.data) : item
      );
      onSchemasChange?.(next);
      return next;
    });
    setMessage({ type: 'success', text: t('contextSchemas.saved') });
  };

  const saveField = async (payload: VoiceContextFieldRequest) => {
    if (!detail) return false;
    const result = editingField
      ? await updateVoiceContextFieldAction(locale, detail.id, editingField.id, payload)
      : await addVoiceContextFieldAction(locale, detail.id, payload);
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return false;
    }
    const fields = editingField
      ? detail.fields.map((field) => (field.id === result.data.id ? result.data : field))
      : [...detail.fields, result.data];
    const next = { ...detail, fields };
    setDetail(next);
    onSchemaDetailChange(next);
    setSchemas((current) =>
      current.map((item) =>
        item.id === detail.id ? { ...item, field_count: fields.length } : item
      )
    );
    setEditingField(null);
    setShowFieldForm(false);
    setMessage({ type: 'success', text: t('contextSchemas.fields.saved') });
    return true;
  };

  const deleteField = async (fieldId: string) => {
    if (!detail) return;
    const result = await deleteVoiceContextFieldAction(locale, detail.id, fieldId);
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    const next = { ...detail, fields: detail.fields.filter((field) => field.id !== fieldId) };
    setDetail(next);
    onSchemaDetailChange(next);
    setSchemas((current) =>
      current.map((item) =>
        item.id === detail.id ? { ...item, field_count: next.fields.length } : item
      )
    );
  };

  const deleteSchema = async () => {
    if (!detail) return;
    const result = await deleteVoiceContextSchemaAction(locale, detail.id);
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    const deletedId = detail.id;
    setDetail(null);
    setMeta({ name: '', description: '' });
    setVersions([]);
    onSchemaDetailChange(null);
    setSchemas((current) => {
      const next = current.filter((item) => item.id !== deletedId);
      onSchemasChange?.(next);
      return next;
    });
    setMessage({ type: 'success', text: t('contextSchemas.deleted') });
  };

  const replaceDetail = async (
    action: () => Promise<
      | { ok: true; data: VoiceContextSchemaResponse }
      | { ok: false; status: number; detail: string }
    >,
    selectResult = false
  ) => {
    const result = await action();
    if (!result.ok) {
      showResultError(result.status, result.detail);
      return;
    }
    setDetail(result.data);
    setMeta({ name: result.data.name, description: result.data.description ?? '' });
    onSchemaDetailChange(result.data);
    if (selectResult) onSchemaSelected(result.data);
    const [, versionsResult] = await Promise.all([
      refreshSchemas(),
      fetchVoiceContextSchemaVersionsAction(
        result.data.agent_config_id,
        result.data.schema_key
      ),
    ]);
    if (versionsResult.ok) setVersions(versionsResult.data);
  };

  if (!agentConfigId) {
    return (
      <div className="rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        {t('contextSchemas.selectAgentFirst')}
      </div>
    );
  }

  const editable = canEdit && detail?.status === 'draft';
  const existingDraft = versions.find((version) => version.status === 'draft');
  const nextPosition = detail?.fields.reduce((max, field) => Math.max(max, field.position), -1) ?? -1;

  return (
    <section className="grid gap-5 lg:grid-cols-[minmax(220px,0.72fr)_minmax(0,1.28fr)]">
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
            {t('contextSchemas.title')}
            <FieldHelp label={t('contextSchemas.title')} required>{t('help.contextSchema')}</FieldHelp>
          </h3>
          {canEdit ? (
            <Button type="button" size="sm" variant="outline" onClick={() => setShowCreate(true)}>
              <Plus className="mr-1.5 size-4" aria-hidden="true" />
              {t('contextSchemas.new')}
            </Button>
          ) : null}
        </div>
        {showCreate ? (
          <div className="space-y-3 rounded-lg border border-primary/20 bg-primary/[0.03] p-3">
            <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
              <span className="flex items-center gap-1.5">
                {t('contextSchemas.schemaKey')}
                <FieldHelp label={t('contextSchemas.schemaKey')} required>{t('help.contextSchemaFields.schemaKey')}</FieldHelp>
              </span>
              <input
                className={FIELD_CLASS}
                value={newSchema.schema_key}
                pattern="^[a-z][a-z0-9_]*$"
                onChange={(event) =>
                  setNewSchema((current) => ({ ...current, schema_key: event.target.value }))
                }
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
              <span className="flex items-center gap-1.5">
                {t('contextSchemas.name')}
                <FieldHelp label={t('contextSchemas.name')} required>{t('help.contextSchemaFields.name')}</FieldHelp>
              </span>
              <input
                className={FIELD_CLASS}
                value={newSchema.name}
                onChange={(event) =>
                  setNewSchema((current) => ({ ...current, name: event.target.value }))
                }
              />
            </label>
            <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
              <span className="flex items-center gap-1.5">
                {t('contextSchemas.description')}
                <FieldHelp label={t('contextSchemas.description')} required={false}>{t('help.contextSchemaFields.description')}</FieldHelp>
              </span>
              <textarea
                className={FIELD_CLASS}
                rows={2}
                value={newSchema.description}
                onChange={(event) =>
                  setNewSchema((current) => ({ ...current, description: event.target.value }))
                }
              />
            </label>
            <div className="flex justify-end gap-2">
              <Button type="button" size="sm" variant="ghost" onClick={() => setShowCreate(false)}>
                {t('common.cancel')}
              </Button>
              <Button
                type="button"
                size="sm"
                disabled={!newSchema.schema_key.trim() || !newSchema.name.trim() || isPending}
                onClick={() => startTransition(() => void createSchema())}
              >
                {t('common.create')}
              </Button>
            </div>
          </div>
        ) : null}
        {isPending ? (
          <p className="flex items-center gap-2 text-xs text-muted-foreground">
            <RefreshCw className="size-3.5 animate-spin" aria-hidden="true" />
            {t('common.loading')}
          </p>
        ) : null}
        <div className="space-y-2" role="list">
          {schemas.map((schema) => (
            <button
              key={schema.id}
              type="button"
              role="listitem"
              onClick={() => startTransition(() => void loadSchema(schema))}
              className={`w-full rounded-lg border p-3 text-left transition hover:border-primary/40 hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                detail?.id === schema.id ? 'border-primary/50 bg-primary/[0.04]' : 'border-border'
              }`}
            >
              <span className="flex items-start justify-between gap-2">
                <span className="min-w-0">
                  <span className="block truncate text-sm font-semibold text-foreground">{schema.name}</span>
                  <span className="mt-1 block font-mono text-[11px] text-muted-foreground">
                    {schema.schema_key} · v{schema.version}
                  </span>
                </span>
                <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              </span>
              <span className="mt-2 flex items-center justify-between gap-2">
                <Badge variant="outline" className="text-[10px]">
                  {t(`contextSchemas.status.${schema.status}`)}
                </Badge>
                <span className="text-[11px] text-muted-foreground">
                  {t('contextSchemas.fieldCount', { count: schema.field_count })}
                </span>
              </span>
            </button>
          ))}
          {schemas.length === 0 && !isPending ? (
            <p className="rounded-lg border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
              {t('contextSchemas.empty')}
            </p>
          ) : null}
        </div>
      </div>

      <div className="min-w-0 space-y-4">
        <div aria-live="polite">
          {message ? (
            <p
              role={message.type === 'error' ? 'alert' : 'status'}
              className={message.type === 'error' ? 'text-sm text-destructive' : 'text-sm text-emerald-600'}
            >
              {message.text}
            </p>
          ) : null}
        </div>
        {!detail ? (
          <div data-testid="context-schema-empty-detail" className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
            <FileKey2 className="mx-auto mb-3 size-7 opacity-60" aria-hidden="true" />
            {t('contextSchemas.selectSchema')}
          </div>
        ) : (
          <>
            <div data-testid="context-schema-detail" className="rounded-lg border border-border bg-card p-4">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-base font-semibold text-foreground">{detail.name}</h3>
                    <Badge variant="outline">{t(`contextSchemas.status.${detail.status}`)}</Badge>
                    <span className="font-mono text-xs text-muted-foreground">v{detail.version}</span>
                  </div>
                  {detail.status !== 'active' ? (
                    <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
                      {t('contextSchemas.notActiveWarning')}
                    </p>
                  ) : null}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant={selectedSchemaId === detail.id ? 'secondary' : 'default'}
                  onClick={() => onSchemaSelected(detail)}
                >
                  <Check className="mr-1.5 size-4" aria-hidden="true" />
                  {selectedSchemaId === detail.id
                    ? t('contextSchemas.selected')
                    : t('contextSchemas.useSchema')}
                </Button>
              </div>

              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-semibold text-muted-foreground">
                  <span className="flex items-center gap-1.5">
                    {t('contextSchemas.name')}
                    <FieldHelp label={t('contextSchemas.name')} required>{t('help.contextSchemaFields.name')}</FieldHelp>
                  </span>
                  <input
                    className={FIELD_CLASS}
                    value={meta.name}
                    disabled={!editable}
                    onChange={(event) => setMeta((current) => ({ ...current, name: event.target.value }))}
                  />
                </label>
                <label className="grid gap-1 text-xs font-semibold text-muted-foreground sm:col-span-2">
                  <span className="flex items-center gap-1.5">
                    {t('contextSchemas.description')}
                    <FieldHelp label={t('contextSchemas.description')} required={false}>{t('help.contextSchemaFields.description')}</FieldHelp>
                  </span>
                  <textarea
                    className={FIELD_CLASS}
                    rows={2}
                    value={meta.description}
                    disabled={!editable}
                    onChange={(event) =>
                      setMeta((current) => ({ ...current, description: event.target.value }))
                    }
                  />
                </label>
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                {editable ? (
                  <>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => startTransition(() => void updateMeta())}
                    >
                      {t('common.save')}
                    </Button>
                    <ActionDialog
                      trigger={
                        <Button type="button" size="sm">
                          <Check className="mr-1.5 size-4" aria-hidden="true" />
                          {t('contextSchemas.activate')}
                        </Button>
                      }
                      title={t('contextSchemas.confirmActivate.title')}
                      description={t('contextSchemas.confirmActivate.description')}
                      confirmLabel={t('contextSchemas.activate')}
                      cancelLabel={t('common.cancel')}
                      busy={isPending}
                      onConfirm={() =>
                        startTransition(() =>
                          void replaceDetail(
                            () => activateVoiceContextSchemaAction(locale, detail.id),
                            true
                          )
                        )
                      }
                    />
                  </>
                ) : canEdit && existingDraft ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => startTransition(() => void loadSchema(existingDraft))}
                  >
                    <Pencil className="mr-1.5 size-4" aria-hidden="true" />
                    {t('contextSchemas.openDraft')}
                  </Button>
                ) : canEdit ? (
                  <ActionDialog
                    trigger={
                      <Button type="button" size="sm" variant="outline">
                        <CopyPlus className="mr-1.5 size-4" aria-hidden="true" />
                        {t('contextSchemas.editAsNewVersion')}
                      </Button>
                    }
                    title={t('contextSchemas.confirmNewVersion.title')}
                    description={t('contextSchemas.confirmNewVersion.description')}
                    confirmLabel={t('contextSchemas.newVersion')}
                    cancelLabel={t('common.cancel')}
                    busy={isPending}
                    onConfirm={() =>
                      startTransition(() =>
                          void replaceDetail(
                            () => forkVoiceContextSchemaVersionAction(locale, detail.id),
                            true
                          )
                      )
                    }
                  />
                ) : null}
                {canEdit && detail.status !== 'archived' ? (
                  <ActionDialog
                    trigger={
                      <Button type="button" size="sm" variant="ghost">
                        <Archive className="mr-1.5 size-4" aria-hidden="true" />
                        {t('contextSchemas.archive')}
                      </Button>
                    }
                    title={t('contextSchemas.confirmArchive.title')}
                    description={t('contextSchemas.confirmArchive.description')}
                    confirmLabel={t('contextSchemas.archive')}
                    cancelLabel={t('common.cancel')}
                    destructive
                    busy={isPending}
                    onConfirm={() =>
                      startTransition(() =>
                        void replaceDetail(() =>
                          archiveVoiceContextSchemaAction(locale, detail.id)
                        )
                      )
                    }
                  />
                ) : null}
                {canEdit && detail.status === 'archived' ? (
                  <ActionDialog
                    trigger={
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label={t('contextSchemas.delete')}
                      >
                        <Trash2 className="size-4" aria-hidden="true" />
                      </Button>
                    }
                    title={t('contextSchemas.confirmDelete.title')}
                    description={t('contextSchemas.confirmDelete.description')}
                    confirmLabel={t('contextSchemas.delete')}
                    cancelLabel={t('common.cancel')}
                    destructive
                    busy={isPending}
                    onConfirm={() => startTransition(() => void deleteSchema())}
                  />
                ) : null}
              </div>
            </div>

            <div className="space-y-3 rounded-lg border border-border bg-card p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-foreground">{t('contextSchemas.fields.title')}</h4>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {editable ? t('contextSchemas.fields.editableHint') : t('contextSchemas.fields.readOnlyHint')}
                  </p>
                </div>
                {editable ? (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setEditingField(null);
                      setShowFieldForm(true);
                    }}
                  >
                    <Plus className="mr-1.5 size-4" aria-hidden="true" />
                    {t('contextSchemas.fields.add')}
                  </Button>
                ) : null}
              </div>
              {showFieldForm ? (
                <ContextFieldForm
                  key={editingField?.id ?? `new-${nextPosition + 1}`}
                  initialField={editingField}
                  nextPosition={nextPosition + 1}
                  busy={isPending}
                  onCancel={() => {
                    setEditingField(null);
                    setShowFieldForm(false);
                  }}
                  onSave={saveField}
                />
              ) : null}
              <ul className="divide-y divide-border">
                {[...detail.fields]
                  .sort((a, b) => a.position - b.position)
                  .map((field) => (
                    <li key={field.id} className="flex items-start justify-between gap-3 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-foreground">
                          {field.label}
                          {field.required ? <span className="ml-1 text-destructive">*</span> : null}
                        </p>
                        <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                          {field.key} · {t(`contextSchemas.fieldTypes.${field.field_type}`)} · #{field.position}
                        </p>
                      </div>
                      {editable ? (
                        <div className="flex shrink-0 gap-1">
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            aria-label={t('contextSchemas.fields.edit')}
                            onClick={() => {
                              setEditingField(field);
                              setShowFieldForm(true);
                            }}
                          >
                            <Pencil className="size-4" aria-hidden="true" />
                          </Button>
                          <ActionDialog
                            trigger={
                              <Button
                                type="button"
                                size="icon"
                                variant="ghost"
                                aria-label={t('contextSchemas.fields.delete')}
                              >
                                <Trash2 className="size-4" aria-hidden="true" />
                              </Button>
                            }
                            title={t('contextSchemas.fields.confirmDelete.title')}
                            description={t('contextSchemas.fields.confirmDelete.description', {
                              label: field.label,
                            })}
                            confirmLabel={t('contextSchemas.fields.delete')}
                            cancelLabel={t('common.cancel')}
                            destructive
                            busy={isPending}
                            onConfirm={() =>
                              startTransition(() => void deleteField(field.id))
                            }
                          />
                        </div>
                      ) : null}
                    </li>
                  ))}
              </ul>
              {detail.fields.length === 0 ? (
                <p className="rounded-md border border-dashed border-border p-4 text-center text-xs text-muted-foreground">
                  {t('contextSchemas.fields.empty')}
                </p>
              ) : null}
            </div>

            {versions.length > 0 ? (
              <div className="rounded-lg border border-border bg-muted/20 p-4">
                <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">
                  {t('contextSchemas.versions')}
                </h4>
                <div className="mt-3 flex flex-wrap gap-2">
                  {versions.map((version) => (
                    <button
                      key={version.id}
                      type="button"
                      aria-pressed={detail.id === version.id}
                      onClick={() => startTransition(() => void loadSchema(version))}
                      className={`rounded-full border px-2.5 py-1 text-xs font-medium transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        detail.id === version.id
                          ? 'border-primary bg-primary/10 text-primary'
                          : 'border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground'
                      }`}
                    >
                      v{version.version} · {t(`contextSchemas.status.${version.status}`)}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
