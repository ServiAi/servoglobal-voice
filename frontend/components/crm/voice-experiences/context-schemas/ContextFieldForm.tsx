'use client';

import { useMemo, useState } from 'react';
import { Plus, Save, X } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import { validateContextField } from '@/lib/voice-experiences/validation';
import type {
  VoiceContextCollectionMode,
  VoiceContextFieldRequest,
  VoiceContextFieldResponse,
  VoiceContextFieldType,
  VoiceContextSensitivity,
} from '@/types/voice-experiences';

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

const FIELD_TYPES: VoiceContextFieldType[] = [
  'text',
  'textarea',
  'email',
  'phone',
  'integer',
  'select',
  'checkbox',
  'date',
];
const COLLECTION_MODES: VoiceContextCollectionMode[] = [
  'ask_if_missing',
  'prefill_and_confirm',
  'trust_prefill',
  'internal_only',
  'collect_during_call',
];

type Props = {
  initialField?: VoiceContextFieldResponse | null;
  nextPosition: number;
  busy?: boolean;
  onCancel: () => void;
  onSave: (payload: VoiceContextFieldRequest) => Promise<boolean>;
};

export function ContextFieldForm({
  initialField,
  nextPosition,
  busy = false,
  onCancel,
  onSave,
}: Props) {
  const t = useTranslations('crm.voiceExperiences');
  const initial = useMemo<VoiceContextFieldRequest>(
    () =>
      initialField ?? {
        key: '',
        label: '',
        description: '',
        field_type: 'text',
        collection_mode: 'ask_if_missing',
        required: false,
        position: nextPosition,
        sensitivity: 'standard',
        validation_json: {},
        options_json: [],
      },
    [initialField, nextPosition]
  );
  const [field, setField] = useState(initial);
  const [optionsText, setOptionsText] = useState(
    initial.options_json.map((option) => `${option.value}|${option.label}`).join('\n')
  );
  const [validationText, setValidationText] = useState(
    Object.keys(initial.validation_json).length ? JSON.stringify(initial.validation_json, null, 2) : ''
  );
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    let validationJson: Record<string, unknown> = {};
    try {
      validationJson = validationText.trim() ? JSON.parse(validationText) : {};
    } catch {
      setError(t('contextSchemas.fields.invalidJson'));
      return;
    }
    const options =
      field.field_type === 'select'
        ? optionsText
            .split('\n')
            .map((line) => line.trim())
            .filter(Boolean)
            .map((line) => {
              const [value, ...label] = line.split('|');
              return { value: value.trim(), label: (label.join('|') || value).trim() };
            })
        : [];
    const payload: VoiceContextFieldRequest = {
      key: field.key.trim(),
      label: field.label.trim(),
      description: field.description?.trim() || null,
      field_type: field.field_type,
      collection_mode: field.collection_mode,
      required: field.required,
      position: initialField?.position ?? nextPosition,
      sensitivity: field.sensitivity,
      validation_json: validationJson,
      options_json: options,
    };
    const errors = validateContextField(payload);
    if (Object.keys(errors).length) {
      setError(t('validation.invalid'));
      return;
    }
    setError(null);
    await onSave(payload);
  };

  return (
    <div data-testid="context-field-form" className="space-y-4 rounded-lg border border-primary/20 bg-primary/[0.03] p-4">
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold text-foreground">
          {initialField ? t('contextSchemas.fields.edit') : t('contextSchemas.fields.add')}
        </h4>
        <Button type="button" variant="ghost" size="icon" onClick={onCancel} aria-label={t('common.cancel')}>
          <X className="size-4" aria-hidden="true" />
        </Button>
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2">
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
          {t('contextSchemas.fields.key')}
          <input
            className={FIELD_CLASS}
            value={field.key}
            disabled={Boolean(initialField)}
            pattern="^[a-z][a-z0-9_]*$"
            onChange={(event) => setField((current) => ({ ...current, key: event.target.value }))}
          />
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
          {t('contextSchemas.fields.label')}
          <input
            className={FIELD_CLASS}
            value={field.label}
            maxLength={160}
            onChange={(event) => setField((current) => ({ ...current, label: event.target.value }))}
          />
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
          {t('contextSchemas.fields.fieldType')}
          <select
            className={FIELD_CLASS}
            value={field.field_type}
            onChange={(event) =>
              setField((current) => ({
                ...current,
                field_type: event.target.value as VoiceContextFieldType,
                options_json: [],
              }))
            }
          >
            {FIELD_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`contextSchemas.fieldTypes.${type}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
          {t('contextSchemas.fields.collectionMode')}
          <select
            className={FIELD_CLASS}
            value={field.collection_mode}
            onChange={(event) =>
              setField((current) => ({
                ...current,
                collection_mode: event.target.value as VoiceContextCollectionMode,
              }))
            }
          >
            {COLLECTION_MODES.map((mode) => (
              <option key={mode} value={mode}>
                {t(`contextSchemas.collectionModes.${mode}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground sm:col-span-2">
          {t('contextSchemas.fields.description')}
          <textarea
            className={FIELD_CLASS}
            rows={2}
            maxLength={1000}
            value={field.description ?? ''}
            onChange={(event) =>
              setField((current) => ({ ...current, description: event.target.value }))
            }
          />
        </label>
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground">
          {t('contextSchemas.fields.sensitivity')}
          <select
            className={FIELD_CLASS}
            value={field.sensitivity}
            onChange={(event) =>
              setField((current) => ({
                ...current,
                sensitivity: event.target.value as VoiceContextSensitivity,
              }))
            }
          >
            <option value="standard">{t('contextSchemas.sensitivity.standard')}</option>
            <option value="sensitive">{t('contextSchemas.sensitivity.sensitive')}</option>
          </select>
        </label>
        <label className="flex min-h-10 items-center gap-2 self-end text-sm font-medium text-foreground">
          <input
            type="checkbox"
            checked={field.required}
            onChange={(event) =>
              setField((current) => ({ ...current, required: event.target.checked }))
            }
          />
          {t('contextSchemas.fields.required')}
        </label>
        {field.field_type === 'select' ? (
          <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground sm:col-span-2">
            {t('contextSchemas.fields.options')}
            <textarea
              className={FIELD_CLASS}
              rows={4}
              value={optionsText}
              placeholder={t('contextSchemas.fields.optionsHint')}
              onChange={(event) => setOptionsText(event.target.value)}
            />
          </label>
        ) : null}
        <label className="grid gap-1.5 text-xs font-semibold text-muted-foreground sm:col-span-2">
          {t('contextSchemas.fields.validation')}
          <textarea
            className={FIELD_CLASS}
            rows={3}
            value={validationText}
            placeholder="{}"
            onChange={(event) => setValidationText(event.target.value)}
          />
        </label>
      </div>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
          {t('common.cancel')}
        </Button>
        <Button type="button" onClick={submit} disabled={busy}>
          {initialField ? <Save className="mr-2 size-4" aria-hidden="true" /> : <Plus className="mr-2 size-4" aria-hidden="true" />}
          {t('common.save')}
        </Button>
      </div>
    </div>
  );
}
