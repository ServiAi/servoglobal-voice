'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Loader2, Pencil, Plus } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import {
  createNotificationRule,
  setNotificationRuleEnabled,
  updateNotificationRule,
} from '@/lib/api/notification-admin';
import type {
  NotificationCatalogResponse,
  NotificationCondition,
  NotificationConditionOperator,
  NotificationRuleCreateRequest,
  NotificationRuleItem,
  NotificationVariableSpec,
} from '@/types/notifications';
import type { WhatsAppTemplateResponse } from '@/types/crm';

type Props = {
  accessToken: string;
  canEdit: boolean;
  catalog: NotificationCatalogResponse | null;
  initialRules: NotificationRuleItem[];
  whatsappTemplates: WhatsAppTemplateResponse[];
};

const LIST_OPERATORS = new Set(['in', 'not_in']);
const NO_VALUE_OPERATORS = new Set(['exists', 'not_exists', 'not_empty']);
const KNOWN_RULE_ERROR_CODES = new Set([
  'duplicate_name',
  'unsupported_event_type',
  'unsupported_capability_key',
  'unsupported_recipient_strategy',
  'recipient_group_key_required',
  'recipient_group_key_invalid_path',
  'condition_invalid',
  'variable_spec_invalid',
  'relative_to_booking_requires_booking_event',
]);

type VariableEntry = { key: string; spec: NotificationVariableSpec };

function emptyFormState(): NotificationRuleCreateRequest {
  return {
    name: '',
    capability_key: '',
    event_type: '',
    template_key: '',
    recipient_strategy: 'event_customer',
    recipient_group_key: '',
    conditions_json: [],
    variable_mapping_json: {},
    schedule_mode: 'immediate',
    schedule_offset_minutes: 0,
    priority: 100,
    enabled: true,
  };
}

function ruleToFormState(rule: NotificationRuleItem): NotificationRuleCreateRequest {
  return {
    name: rule.name,
    capability_key: rule.capability_key,
    event_type: rule.event_type,
    template_key: rule.template_key ?? '',
    recipient_strategy: rule.recipient_strategy,
    recipient_group_key: rule.recipient_group_key ?? '',
    conditions_json: rule.conditions_json,
    variable_mapping_json: rule.variable_mapping_json,
    schedule_mode: rule.schedule_mode,
    schedule_offset_minutes: rule.schedule_offset_minutes,
    priority: rule.priority,
    enabled: rule.enabled,
  };
}

export function RulesPanel({ accessToken, canEdit, catalog, initialRules, whatsappTemplates }: Props) {
  const t = useTranslations('crm.notifications.rules');
  const [rules, setRules] = useState(initialRules);
  const [editing, setEditing] = useState<NotificationRuleItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyRuleId, setBusyRuleId] = useState<string | null>(null);

  const drawerOpen = creating || editing !== null;

  const closeDrawer = () => {
    setCreating(false);
    setEditing(null);
  };

  const handleSaved = (rule: NotificationRuleItem) => {
    setRules((current) => {
      const exists = current.some((item) => item.id === rule.id);
      return exists ? current.map((item) => (item.id === rule.id ? rule : item)) : [...current, rule];
    });
    closeDrawer();
  };

  const toggleEnabled = async (rule: NotificationRuleItem) => {
    setBusyRuleId(rule.id);
    const result = await setNotificationRuleEnabled(accessToken, rule.id, !rule.enabled);
    setBusyRuleId(null);
    if (result.ok) {
      setRules((current) => current.map((item) => (item.id === rule.id ? result.data : item)));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {canEdit && (
        <div className="flex justify-end">
          <Button type="button" className="gap-2" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            {t('form.createTitle')}
          </Button>
        </div>
      )}

      {rules.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
          <p>{t('empty')}</p>
          {canEdit && <p>{t('emptyAction')}</p>}
        </div>
      ) : (
        <>
          <div className="hidden overflow-x-auto rounded-xl border border-border md:block">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">{t('columns.name')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.event')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.template')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.recipient')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.schedule')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.priority')}</th>
                  <th className="px-4 py-3 font-medium">{t('columns.status')}</th>
                  {canEdit && <th className="px-4 py-3 font-medium">{t('columns.actions')}</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rules.map((rule) => (
                  <tr key={rule.id}>
                    <td className="px-4 py-3 font-medium text-foreground">{rule.name}</td>
                    <td className="px-4 py-3 text-muted-foreground">{rule.event_type}</td>
                    <td className="px-4 py-3 text-muted-foreground">{rule.template_key || '—'}</td>
                    <td className="px-4 py-3 text-muted-foreground">{t(`form.strategies.${rule.recipient_strategy}`)}</td>
                    <td className="px-4 py-3 text-muted-foreground">
                      {rule.schedule_mode === 'immediate' ? t('form.scheduleModes.immediate') : `${rule.schedule_offset_minutes} min`}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{rule.priority}</td>
                    <td className="px-4 py-3">
                      <RuleStatusBadge rule={rule} />
                    </td>
                    {canEdit && (
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <Button type="button" variant="outline" size="sm" onClick={() => setEditing(rule)}>
                            <Pencil className="size-3.5" aria-hidden="true" />
                            <span className="sr-only sm:not-sr-only sm:ml-1.5">{t('actions.edit')}</span>
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            disabled={busyRuleId === rule.id}
                            onClick={() => toggleEnabled(rule)}
                          >
                            {busyRuleId === rule.id && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                            {rule.enabled ? t('actions.deactivate') : t('actions.activate')}
                          </Button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="flex flex-col gap-3 md:hidden">
            {rules.map((rule) => (
              <li key={rule.id} className="rounded-xl border border-border bg-card p-4 shadow-xs">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium text-foreground">{rule.name}</p>
                  <RuleStatusBadge rule={rule} />
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <dt>{t('columns.event')}</dt>
                  <dd className="text-right">{rule.event_type}</dd>
                  <dt>{t('columns.template')}</dt>
                  <dd className="text-right">{rule.template_key || '—'}</dd>
                  <dt>{t('columns.priority')}</dt>
                  <dd className="text-right">{rule.priority}</dd>
                </dl>
                {canEdit && (
                  <div className="mt-3 flex gap-2">
                    <Button type="button" variant="outline" size="sm" className="flex-1" onClick={() => setEditing(rule)}>
                      {t('actions.edit')}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="flex-1"
                      disabled={busyRuleId === rule.id}
                      onClick={() => toggleEnabled(rule)}
                    >
                      {rule.enabled ? t('actions.deactivate') : t('actions.activate')}
                    </Button>
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {drawerOpen && (
        <RuleFormDialog
          accessToken={accessToken}
          catalog={catalog}
          whatsappTemplates={whatsappTemplates}
          rule={editing}
          onClose={closeDrawer}
          onSaved={handleSaved}
        />
      )}
    </div>
  );
}

function RuleStatusBadge({ rule }: { rule: NotificationRuleItem }) {
  const t = useTranslations('crm.notifications.rules.status');
  if (rule.configuration_error) {
    return (
      <span className="inline-flex min-h-7 items-center rounded-full border border-destructive/25 bg-destructive/10 px-2.5 py-1 text-xs font-semibold text-destructive">
        {t('invalid')}
      </span>
    );
  }
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        rule.enabled
          ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'border-border bg-muted text-muted-foreground'
      }`}
    >
      {rule.enabled ? t('active') : t('inactive')}
    </span>
  );
}

function RuleFormDialog({
  accessToken,
  catalog,
  whatsappTemplates,
  rule,
  onClose,
  onSaved,
}: {
  accessToken: string;
  catalog: NotificationCatalogResponse | null;
  whatsappTemplates: WhatsAppTemplateResponse[];
  rule: NotificationRuleItem | null;
  onClose: () => void;
  onSaved: (rule: NotificationRuleItem) => void;
}) {
  const t = useTranslations('crm.notifications.rules.form');
  const [form, setForm] = useState<NotificationRuleCreateRequest>(rule ? ruleToFormState(rule) : emptyFormState());
  const [busy, setBusy] = useState(false);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const set = <K extends keyof NotificationRuleCreateRequest>(key: K, value: NotificationRuleCreateRequest[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const conditions = form.conditions_json ?? [];
  const variables = Object.entries(form.variable_mapping_json ?? {}).map(([key, spec]) => ({ key, spec }));

  const updateConditions = (next: NotificationCondition[]) => set('conditions_json', next);
  const updateVariables = (next: VariableEntry[]) => {
    const mapping: Record<string, NotificationVariableSpec> = {};
    next.forEach((entry) => {
      if (entry.key) mapping[entry.key] = entry.spec;
    });
    set('variable_mapping_json', mapping);
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setErrorCode(null);
    const payload: NotificationRuleCreateRequest = {
      ...form,
      recipient_group_key: form.recipient_group_key || null,
      schedule_offset_minutes: form.schedule_mode === 'immediate' ? 0 : Number(form.schedule_offset_minutes) || 0,
    };
    const result = rule
      ? await updateNotificationRule(accessToken, rule.id, payload)
      : await createNotificationRule(accessToken, payload);
    setBusy(false);
    if (!result.ok) {
      setErrorCode(result.detail);
      return;
    }
    onSaved(result.data);
  };

  const errorMessageKey = errorCode && KNOWN_RULE_ERROR_CODES.has(errorCode) ? errorCode : 'generic';

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{rule ? t('editTitle') : t('createTitle')}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {errorCode && (
            <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {t(`errors.${errorMessageKey}`)}
            </p>
          )}

          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1 text-sm sm:col-span-2">
              <span>{t('name')}</span>
              <input
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.name}
                onChange={(event) => set('name', event.target.value)}
                required
                maxLength={160}
              />
            </label>

            <label className="space-y-1 text-sm">
              <span>{t('capability')}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.capability_key}
                onChange={(event) => set('capability_key', event.target.value)}
                required
              >
                <option value="">—</option>
                {catalog?.capability_keys.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span>{t('event')}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.event_type}
                onChange={(event) => set('event_type', event.target.value)}
                required
              >
                <option value="">—</option>
                {catalog?.event_types.map((key) => (
                  <option key={key} value={key}>
                    {key}
                  </option>
                ))}
              </select>
            </label>

            <label className="space-y-1 text-sm">
              <span>{t('template')}</span>
              {whatsappTemplates.length > 0 ? (
                <select
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={form.template_key}
                  onChange={(event) => set('template_key', event.target.value)}
                  required
                >
                  <option value="">—</option>
                  {whatsappTemplates.map((template) => (
                    <option key={template.id} value={template.template_key}>
                      {template.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={form.template_key}
                  onChange={(event) => set('template_key', event.target.value)}
                  required
                  maxLength={120}
                />
              )}
            </label>

            <label className="space-y-1 text-sm">
              <span>{t('recipientStrategy')}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.recipient_strategy}
                onChange={(event) => set('recipient_strategy', event.target.value)}
                required
              >
                {catalog?.recipient_strategies.map((key) => (
                  <option key={key} value={key}>
                    {t(`strategies.${key}`)}
                  </option>
                ))}
              </select>
            </label>

            {form.recipient_strategy !== 'event_customer' && (
              <label className="space-y-1 text-sm">
                <span>{t('recipientGroup')}</span>
                <input
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={form.recipient_group_key ?? ''}
                  onChange={(event) => set('recipient_group_key', event.target.value)}
                  required
                  maxLength={80}
                />
              </label>
            )}

            <label className="space-y-1 text-sm">
              <span>{t('scheduleMode')}</span>
              <select
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.schedule_mode}
                onChange={(event) => set('schedule_mode', event.target.value)}
              >
                {catalog?.schedule_modes.map((key) => (
                  <option key={key} value={key}>
                    {t(`scheduleModes.${key}`)}
                  </option>
                ))}
              </select>
            </label>

            {form.schedule_mode === 'relative_to_booking' && (
              <label className="space-y-1 text-sm">
                <span>{t('scheduleOffset')}</span>
                <input
                  type="number"
                  className="w-full rounded-md border border-border bg-background px-3 py-2"
                  value={form.schedule_offset_minutes}
                  onChange={(event) => set('schedule_offset_minutes', Number(event.target.value))}
                />
                <span className="block text-xs text-muted-foreground">{t('scheduleHint')}</span>
              </label>
            )}

            <label className="space-y-1 text-sm">
              <span>{t('priority')}</span>
              <input
                type="number"
                className="w-full rounded-md border border-border bg-background px-3 py-2"
                value={form.priority}
                onChange={(event) => set('priority', Number(event.target.value))}
              />
            </label>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-4 rounded border-border"
                checked={form.enabled}
                onChange={(event) => set('enabled', event.target.checked)}
              />
              <span>{t('enabled')}</span>
            </label>
          </div>

          <ConditionsBuilder
            conditions={conditions}
            operators={catalog?.condition_operators ?? []}
            onChange={updateConditions}
          />

          <VariablesBuilder
            variables={variables}
            sources={catalog?.variable_sources ?? []}
            formats={catalog?.variable_formats ?? []}
            onChange={updateVariables}
          />

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
              {t('save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ConditionsBuilder({
  conditions,
  operators,
  onChange,
}: {
  conditions: NotificationCondition[];
  operators: string[];
  onChange: (next: NotificationCondition[]) => void;
}) {
  const t = useTranslations('crm.notifications.rules.form');

  const update = (index: number, patch: Partial<NotificationCondition>) => {
    onChange(conditions.map((condition, i) => (i === index ? { ...condition, ...patch } : condition)));
  };

  return (
    <fieldset className="space-y-2 border-t border-border pt-4">
      <legend className="text-sm font-medium text-foreground">{t('conditions')}</legend>
      {conditions.map((condition, index) => (
        <div key={index} className="grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-center">
          <input
            aria-label="field"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={condition.field}
            onChange={(event) => update(index, { field: event.target.value })}
            placeholder="booking.status"
          />
          <select
            aria-label="operator"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={condition.operator}
            onChange={(event) => update(index, { operator: event.target.value as NotificationConditionOperator })}
          >
            {operators.map((operator) => (
              <option key={operator} value={operator}>
                {operator}
              </option>
            ))}
          </select>
          {!NO_VALUE_OPERATORS.has(condition.operator) && (
            <input
              aria-label="value"
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={LIST_OPERATORS.has(condition.operator) && Array.isArray(condition.value) ? condition.value.join(',') : (condition.value as string) ?? ''}
              onChange={(event) =>
                update(index, {
                  value: LIST_OPERATORS.has(condition.operator)
                    ? event.target.value.split(',').map((item) => item.trim()).filter(Boolean)
                    : event.target.value,
                })
              }
            />
          )}
          <Button type="button" variant="ghost" size="sm" onClick={() => onChange(conditions.filter((_, i) => i !== index))}>
            {t('removeCondition')}
          </Button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange([...conditions, { field: '', operator: 'equals', value: '' }])}
      >
        {t('addCondition')}
      </Button>
    </fieldset>
  );
}

function VariablesBuilder({
  variables,
  sources,
  formats,
  onChange,
}: {
  variables: VariableEntry[];
  sources: string[];
  formats: string[];
  onChange: (next: VariableEntry[]) => void;
}) {
  const t = useTranslations('crm.notifications.rules.form');
  const tCommon = useTranslations('crm.notifications.common');

  const update = (index: number, patch: Partial<VariableEntry> | Partial<NotificationVariableSpec>) => {
    onChange(
      variables.map((entry, i) => {
        if (i !== index) return entry;
        if ('key' in patch) {
          return { ...entry, key: (patch as Partial<VariableEntry>).key ?? entry.key };
        }
        return { ...entry, spec: { ...entry.spec, ...(patch as Partial<NotificationVariableSpec>) } };
      })
    );
  };

  return (
    <fieldset className="space-y-2 border-t border-border pt-4">
      <legend className="text-sm font-medium text-foreground">{t('variables')}</legend>
      {variables.map((entry, index) => (
        <div key={index} className="grid gap-2 rounded-md border border-border p-3 sm:grid-cols-2">
          <input
            aria-label="variable key"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={entry.key}
            placeholder="customer_name"
            onChange={(event) => update(index, { key: event.target.value })}
          />
          <select
            aria-label="source"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={entry.spec.source}
            onChange={(event) => update(index, { source: event.target.value as NotificationVariableSpec['source'] })}
          >
            {sources.map((source) => (
              <option key={source} value={source}>
                {source}
              </option>
            ))}
          </select>
          {entry.spec.source === 'literal' ? (
            <input
              aria-label="value"
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={(entry.spec.value as string) ?? ''}
              onChange={(event) => update(index, { value: event.target.value })}
              placeholder="value"
            />
          ) : (
            <input
              aria-label="path"
              className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
              value={entry.spec.path ?? ''}
              onChange={(event) => update(index, { path: event.target.value })}
              placeholder="booking.start_at"
            />
          )}
          <select
            aria-label="format"
            className="rounded-md border border-border bg-background px-2 py-1.5 text-sm"
            value={entry.spec.format ?? 'string'}
            onChange={(event) => update(index, { format: event.target.value as NotificationVariableSpec['format'] })}
          >
            {formats.map((format) => (
              <option key={format} value={format}>
                {format}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="size-4 rounded border-border"
              checked={entry.spec.required ?? true}
              onChange={(event) => update(index, { required: event.target.checked })}
            />
            {tCommon('required')}
          </label>
          <div className="sm:col-span-2">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onChange(variables.filter((_, i) => i !== index))}
            >
              {t('removeVariable')}
            </Button>
          </div>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() =>
          onChange([...variables, { key: '', spec: { source: 'event_field', path: '', format: 'string', required: true } }])
        }
      >
        {t('addVariable')}
      </Button>
    </fieldset>
  );
}
