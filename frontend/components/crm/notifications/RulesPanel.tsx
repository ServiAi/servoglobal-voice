'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, CheckCircle2, Clock3, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { FieldHelp } from '@/components/crm/integrations/FieldHelp';
import {
  createNotificationRuleAction,
  deleteNotificationRuleAction,
  setNotificationRuleEnabledAction,
  updateNotificationRuleAction,
} from '@/app/[locale]/crm/settings/notifications/actions';
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
  canEdit: boolean;
  catalog: NotificationCatalogResponse | null;
  initialRules: NotificationRuleItem[];
  whatsappTemplates: WhatsAppTemplateResponse[];
};

const LIST_OPERATORS = new Set(['in', 'not_in']);
const NO_VALUE_OPERATORS = new Set(['exists', 'not_exists', 'not_empty']);
const NUMERIC_OPERATORS = new Set([
  'greater_than',
  'greater_than_or_equal',
  'less_than',
  'less_than_or_equal',
]);
const KNOWN_RULE_ERROR_CODES = new Set([
  'duplicate_name',
  'unsupported_event_type',
  'unsupported_capability_key',
  'unsupported_recipient_strategy',
  'recipient_group_key_required',
  'recipient_group_key_invalid_path',
  'condition_invalid',
  'condition_numeric_value_required',
  'variable_spec_invalid',
  'relative_to_booking_requires_booking_event',
  'whatsapp_template_not_approved',
  'template_variable_mapping_missing',
  'template_variables_malformed',
]);

type VariableEntry = { key: string; spec: NotificationVariableSpec };

type TemplateParameter = { key: string; label?: string };

const FIELD_CLASS =
  'min-h-10 w-full rounded-md border border-border bg-background px-3 py-2 text-sm shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const SMALL_FIELD_CLASS =
  'min-h-9 w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-sm shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';
const FORM_SECTION_CLASS = 'rounded-lg border border-border bg-muted/20 p-4';
const TABLE_WRAP_CLASS = 'hidden';
const TABLE_HEAD_CLASS = 'bg-muted/60 text-xs uppercase tracking-wide text-muted-foreground';
const TABLE_ROW_CLASS = 'transition-colors hover:bg-muted/30';

function HelpLabel({ label, help, required = false }: { label: string; help: string; required?: boolean }) {
  return (
    <span className="flex items-center gap-1 font-medium text-foreground">
      {label}
      <FieldHelp label={label} required={required}>{help}</FieldHelp>
    </span>
  );
}

function approvedTemplateParameters(template: WhatsAppTemplateResponse): TemplateParameter[] | null {
  const variables = template.variables as {
    source?: string;
    meta_status?: string;
    parameters?: TemplateParameter[];
  };
  if (
    template.status !== 'active' ||
    variables?.source !== 'meta_sync' ||
    variables?.meta_status !== 'APPROVED'
  ) {
    return null;
  }
  return Array.isArray(variables.parameters) ? variables.parameters : [];
}

function isApprovedTemplate(template: WhatsAppTemplateResponse): boolean {
  return approvedTemplateParameters(template) !== null;
}

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

export function RulesPanel({ canEdit, catalog, initialRules, whatsappTemplates }: Props) {
  const t = useTranslations('crm.notifications.rules');
  const [rules, setRules] = useState(initialRules);
  const [editing, setEditing] = useState<NotificationRuleItem | null>(null);
  const [creating, setCreating] = useState(false);
  const [busyRuleId, setBusyRuleId] = useState<string | null>(null);
  const [toggleErrorId, setToggleErrorId] = useState<string | null>(null);
  const [confirmDisable, setConfirmDisable] = useState<NotificationRuleItem | null>(null);
  const [deleteErrorId, setDeleteErrorId] = useState<string | null>(null);
  const [deleteErrorCode, setDeleteErrorCode] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<NotificationRuleItem | null>(null);

  const approvedTemplates = whatsappTemplates.filter(isApprovedTemplate);
  const hasApprovedTemplates = approvedTemplates.length > 0;
  const activeRules = rules.filter((rule) => rule.enabled && !rule.configuration_error).length;
  const invalidRules = rules.filter((rule) => rule.configuration_error).length;

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

  const applyToggle = async (rule: NotificationRuleItem, nextEnabled: boolean) => {
    setBusyRuleId(rule.id);
    setToggleErrorId(null);
    const result = await setNotificationRuleEnabledAction(rule.id, nextEnabled);
    setBusyRuleId(null);
    if (!result.ok) {
      setToggleErrorId(rule.id);
      return;
    }
    setRules((current) => current.map((item) => (item.id === rule.id ? result.data : item)));
  };

  const requestToggle = (rule: NotificationRuleItem) => {
    if (rule.enabled) {
      setConfirmDisable(rule);
      return;
    }
    applyToggle(rule, true);
  };

  const applyDelete = async (rule: NotificationRuleItem) => {
    setBusyRuleId(rule.id);
    setDeleteErrorId(null);
    const result = await deleteNotificationRuleAction(rule.id);
    setBusyRuleId(null);
    if (!result.ok) {
      setDeleteErrorId(rule.id);
      setDeleteErrorCode(result.detail);
      return;
    }
    setRules((current) => current.filter((item) => item.id !== rule.id));
  };

  return (
    <div className="flex flex-col gap-5">
      <div className="rounded-lg border border-border bg-card shadow-xs">
        <div className="flex flex-col gap-4 border-b border-border p-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="grid gap-2 sm:grid-cols-3">
            <RuleCountBadge icon={CheckCircle2} label={t('status.active')} value={activeRules} tone="success" />
            <RuleCountBadge icon={Clock3} label={t('status.inactive')} value={Math.max(rules.length - activeRules - invalidRules, 0)} />
            <RuleCountBadge icon={AlertTriangle} label={t('status.invalid')} value={invalidRules} tone="danger" />
          </div>
          {canEdit && hasApprovedTemplates && (
            <Button type="button" className="gap-2 self-start lg:self-auto" onClick={() => setCreating(true)}>
              <Plus className="size-4" aria-hidden="true" />
              {t('form.createTitle')}
            </Button>
          )}
        </div>

        {canEdit && !hasApprovedTemplates && (
          <div role="status" className="m-4 rounded-lg border border-amber-500/25 bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-200">
            {t('noApprovedTemplates')}
          </div>
        )}

        {rules.length === 0 ? (
          <div className="m-4 rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center text-sm text-muted-foreground">
            <p className="font-medium text-foreground">{t('empty')}</p>
            {canEdit && <p className="mt-1">{t('emptyAction')}</p>}
          </div>
        ) : (
          <div className="p-4">
            <div className={TABLE_WRAP_CLASS}>
            <table className="w-full text-left text-sm">
              <thead className={TABLE_HEAD_CLASS}>
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
                  <tr key={rule.id} className={TABLE_ROW_CLASS}>
                    <td className="px-4 py-3">
                      <div className="max-w-[260px]">
                        <p className="font-medium text-foreground">{rule.name}</p>
                        <p className="mt-1 truncate text-xs text-muted-foreground">{rule.capability_key}</p>
                      </div>
                    </td>
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
                        <div className="flex flex-col gap-1">
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
                              onClick={() => requestToggle(rule)}
                            >
                              {busyRuleId === rule.id && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                              {rule.enabled ? t('actions.deactivate') : t('actions.activate')}
                            </Button>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              className="text-destructive hover:text-destructive"
                              disabled={busyRuleId === rule.id}
                              onClick={() => setConfirmDelete(rule)}
                            >
                              <Trash2 className="size-3.5" aria-hidden="true" />
                              <span className="sr-only sm:not-sr-only sm:ml-1.5">{t('actions.delete')}</span>
                            </Button>
                          </div>
                          {toggleErrorId === rule.id && (
                            <p role="alert" className="text-xs text-destructive">
                              {t('actions.toggleError')}
                            </p>
                          )}
                          {deleteErrorId === rule.id && (
                            <p role="alert" className="text-xs text-destructive">
                              {deleteErrorCode === 'rule_has_deliveries'
                                ? t('actions.deleteErrorHasDeliveries')
                                : t('actions.deleteError')}
                            </p>
                          )}
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <ul className="grid gap-3 lg:grid-cols-2">
            {rules.map((rule) => (
              <li key={rule.id} className="min-w-0 rounded-lg border border-border bg-background p-4 shadow-xs transition-colors hover:border-primary/25">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate font-semibold text-foreground">{rule.name}</p>
                    <p className="mt-1 truncate text-xs text-muted-foreground">{rule.capability_key}</p>
                  </div>
                  <RuleStatusBadge rule={rule} />
                </div>
                <dl className="mt-4 grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] gap-x-3 gap-y-2 border-y border-border py-3 text-xs text-muted-foreground">
                  <dt>{t('columns.event')}</dt>
                  <dd className="truncate text-right font-medium text-foreground">{rule.event_type}</dd>
                  <dt>{t('columns.template')}</dt>
                  <dd className="truncate text-right font-medium text-foreground">{rule.template_key || '—'}</dd>
                  <dt>{t('columns.recipient')}</dt>
                  <dd className="truncate text-right font-medium text-foreground">{t(`form.strategies.${rule.recipient_strategy}`)}</dd>
                  <dt>{t('columns.schedule')}</dt>
                  <dd className="text-right font-medium text-foreground">
                    {rule.schedule_mode === 'immediate' ? t('form.scheduleModes.immediate') : `${rule.schedule_offset_minutes} min`}
                  </dd>
                  <dt>{t('columns.priority')}</dt>
                  <dd className="text-right font-medium text-foreground">{rule.priority}</dd>
                </dl>
                {canEdit && (
                  <div className="mt-3 flex flex-col gap-2">
                    <div className="flex flex-wrap items-center justify-end gap-2">
                      <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => setEditing(rule)}>
                        <Pencil className="size-3.5" aria-hidden="true" />
                        {t('actions.edit')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-2"
                        disabled={busyRuleId === rule.id}
                        onClick={() => requestToggle(rule)}
                      >
                        {busyRuleId === rule.id && <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />}
                        {rule.enabled ? t('actions.deactivate') : t('actions.activate')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="gap-2 text-destructive hover:text-destructive"
                        disabled={busyRuleId === rule.id}
                        onClick={() => setConfirmDelete(rule)}
                      >
                        <Trash2 className="size-3.5" aria-hidden="true" />
                        {t('actions.delete')}
                      </Button>
                    </div>
                    {toggleErrorId === rule.id && (
                      <p role="alert" className="text-xs text-destructive">
                        {t('actions.toggleError')}
                      </p>
                    )}
                    {deleteErrorId === rule.id && (
                      <p role="alert" className="text-xs text-destructive">
                        {deleteErrorCode === 'rule_has_deliveries'
                          ? t('actions.deleteErrorHasDeliveries')
                          : t('actions.deleteError')}
                      </p>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
          </div>
        )}
      </div>

      {confirmDisable && (
        <ConfirmDisableRuleDialog
          busy={busyRuleId === confirmDisable.id}
          onCancel={() => setConfirmDisable(null)}
          onConfirm={async () => {
            const rule = confirmDisable;
            await applyToggle(rule, false);
            setConfirmDisable(null);
          }}
        />
      )}

      {confirmDelete && (
        <ConfirmDeleteRuleDialog
          busy={busyRuleId === confirmDelete.id}
          onCancel={() => setConfirmDelete(null)}
          onConfirm={async () => {
            const rule = confirmDelete;
            await applyDelete(rule);
            setConfirmDelete(null);
          }}
        />
      )}

      {drawerOpen && (
        <RuleFormDialog
          catalog={catalog}
          whatsappTemplates={approvedTemplates}
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

function RuleCountBadge({
  icon: Icon,
  label,
  value,
  tone = 'neutral',
}: {
  icon: typeof CheckCircle2;
  label: string;
  value: number;
  tone?: 'neutral' | 'success' | 'danger';
}) {
  const styles = {
    neutral: 'border-border bg-background text-muted-foreground',
    success: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
    danger: 'border-destructive/25 bg-destructive/10 text-destructive',
  };

  return (
    <div className={`flex min-h-12 items-center gap-3 rounded-md border px-3 py-2 ${styles[tone]}`}>
      <Icon className="size-4 shrink-0" aria-hidden="true" />
      <div>
        <p className="text-base font-semibold leading-none text-foreground">{value}</p>
        <p className="mt-1 text-xs">{label}</p>
      </div>
    </div>
  );
}

function ConfirmDisableRuleDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const t = useTranslations('crm.notifications.rules.confirmDisable');
  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md border-amber-500/20 p-0">
        <DialogHeader className="border-b border-border bg-amber-500/10 p-5 pr-12">
          <div className="mb-2 flex size-10 items-center justify-center rounded-full border border-amber-500/25 bg-background text-amber-700 dark:text-amber-300">
            <Clock3 className="size-5" aria-hidden="true" />
          </div>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="p-5">
          <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
            {t('cancel')}
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={busy} className="gap-2">
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDeleteRuleDialog({
  busy,
  onCancel,
  onConfirm,
}: {
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const t = useTranslations('crm.notifications.rules.confirmDelete');
  return (
    <Dialog open onOpenChange={(open) => !open && onCancel()}>
      <DialogContent className="max-w-md border-destructive/20 p-0">
        <DialogHeader className="border-b border-border bg-destructive/10 p-5 pr-12">
          <div className="mb-2 flex size-10 items-center justify-center rounded-full border border-destructive/25 bg-background text-destructive">
            <Trash2 className="size-5" aria-hidden="true" />
          </div>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>
        <DialogFooter className="p-5">
          <Button type="button" variant="outline" onClick={onCancel} disabled={busy}>
            {t('cancel')}
          </Button>
          <Button type="button" variant="destructive" onClick={onConfirm} disabled={busy} className="gap-2">
            {busy && <Loader2 className="size-4 animate-spin" aria-hidden="true" />}
            {t('confirm')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RuleFormDialog({
  catalog,
  whatsappTemplates,
  rule,
  onClose,
  onSaved,
}: {
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

  const selectedTemplate = whatsappTemplates.find((template) => template.template_key === form.template_key) ?? null;
  const requiredParameters = selectedTemplate ? approvedTemplateParameters(selectedTemplate) ?? [] : [];

  const isMappingSatisfied = (spec: NotificationVariableSpec | undefined): boolean => {
    if (!spec) return false;
    if (spec.source === 'literal') {
      return spec.value !== undefined && spec.value !== null && spec.value !== '';
    }
    return Boolean(spec.path) && (spec.required !== false || (spec.default !== undefined && spec.default !== null));
  };

  const missingRequiredParameters = requiredParameters.filter(
    (param) => !isMappingSatisfied(form.variable_mapping_json?.[param.key])
  );

  const hasInvalidNumericCondition = conditions.some(
    (condition) =>
      NUMERIC_OPERATORS.has(condition.operator) &&
      (typeof condition.value !== 'number' || !Number.isFinite(condition.value))
  );

  const selectTemplate = (templateKey: string) => {
    const template = whatsappTemplates.find((item) => item.template_key === templateKey) ?? null;
    const parameters = template ? approvedTemplateParameters(template) ?? [] : [];
    const nextMapping: Record<string, NotificationVariableSpec> = { ...(form.variable_mapping_json ?? {}) };
    parameters.forEach((param) => {
      if (!nextMapping[param.key]) {
        nextMapping[param.key] = { source: 'literal', value: '', format: 'string', required: true };
      }
    });
    setForm((current) => ({ ...current, template_key: templateKey, variable_mapping_json: nextMapping }));
  };

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
      ? await updateNotificationRuleAction(rule.id, payload)
      : await createNotificationRuleAction(payload);
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
      <DialogContent className="h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-4xl grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:h-[calc(100dvh-2rem)] sm:w-full lg:max-h-[900px]">
        <DialogHeader className="border-b border-border bg-muted/30 p-4 pr-12 sm:p-5 sm:pr-12">
          <DialogTitle>{rule ? t('editTitle') : t('createTitle')}</DialogTitle>
          <DialogDescription>{t('template')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto]">
          <div className="min-h-0 space-y-5 overflow-y-auto overscroll-contain p-4 sm:p-5">
          {errorCode && (
            <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {t(`errors.${errorMessageKey}`)}
            </p>
          )}

          <div className={`${FORM_SECTION_CLASS} grid gap-3 sm:grid-cols-2`}>
            <label className="space-y-1 text-sm sm:col-span-2">
              <HelpLabel label={t('name')} help={t('help.name')} required />
              <input
                className={FIELD_CLASS}
                value={form.name}
                onChange={(event) => set('name', event.target.value)}
                required
                maxLength={160}
              />
            </label>

            <label className="space-y-1 text-sm">
              <HelpLabel label={t('capability')} help={t('help.capability')} required />
              <select
                className={FIELD_CLASS}
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
              <HelpLabel label={t('event')} help={t('help.event')} required />
              <select
                className={FIELD_CLASS}
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

            <label className="space-y-1 text-sm sm:col-span-2">
              <HelpLabel label={t('template')} help={t('help.template')} required />
              <select
                className={FIELD_CLASS}
                value={form.template_key}
                onChange={(event) => selectTemplate(event.target.value)}
                required
              >
                <option value="">—</option>
                {whatsappTemplates.map((template) => (
                  <option key={template.id} value={template.template_key}>
                    {template.name}
                  </option>
                ))}
                {form.template_key &&
                  !whatsappTemplates.some((template) => template.template_key === form.template_key) && (
                    <option value={form.template_key} disabled>
                      {form.template_key}
                    </option>
                  )}
              </select>
              {requiredParameters.length > 0 && (
                <span className="block text-xs text-muted-foreground">
                  {t('requiredParameters', { params: requiredParameters.map((param) => param.key).join(', ') })}
                </span>
              )}
            </label>

            <label className="space-y-1 text-sm">
              <HelpLabel label={t('recipientStrategy')} help={t('help.recipientStrategy')} required />
              <select
                className={FIELD_CLASS}
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
                <HelpLabel label={t('recipientGroup')} help={t('help.recipientGroup')} required />
                <input
                  className={FIELD_CLASS}
                  value={form.recipient_group_key ?? ''}
                  onChange={(event) => set('recipient_group_key', event.target.value)}
                  required
                  maxLength={80}
                />
              </label>
            )}

            <label className="space-y-1 text-sm">
              <HelpLabel label={t('scheduleMode')} help={t('help.scheduleMode')} required />
              <select
                className={FIELD_CLASS}
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
                <HelpLabel label={t('scheduleOffset')} help={t('help.scheduleOffset')} required />
                <input
                  type="number"
                  className={FIELD_CLASS}
                  value={form.schedule_offset_minutes}
                  onChange={(event) => set('schedule_offset_minutes', Number(event.target.value))}
                />
                <span className="block text-xs text-muted-foreground">{t('scheduleHint')}</span>
              </label>
            )}

            <label className="space-y-1 text-sm">
              <HelpLabel label={t('priority')} help={t('help.priority')} />
              <input
                type="number"
                className={FIELD_CLASS}
                value={form.priority}
                onChange={(event) => set('priority', Number(event.target.value))}
              />
            </label>

            <div className="flex items-center gap-2 text-sm">
              <input
                id="notification-rule-enabled"
                type="checkbox"
                className="size-4 rounded border-border"
                checked={form.enabled}
                onChange={(event) => set('enabled', event.target.checked)}
              />
              <label htmlFor="notification-rule-enabled">{t('enabled')}</label>
              <FieldHelp label={t('enabled')} required={false}>{t('help.enabled')}</FieldHelp>
            </div>
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

          {missingRequiredParameters.length > 0 && (
            <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">
              {t('missingRequiredParameters', { params: missingRequiredParameters.map((param) => param.key).join(', ') })}
            </p>
          )}

          {hasInvalidNumericCondition && (
            <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-xs text-destructive">{t('errors.condition_numeric_value_required')}</p>
          )}
          </div>

          <DialogFooter className="border-t border-border bg-background p-4 sm:px-5">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('cancel')}
            </Button>
            <Button
              type="submit"
              disabled={busy || missingRequiredParameters.length > 0 || hasInvalidNumericCondition}
              className="gap-2"
            >
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

  const changeOperator = (index: number, operator: NotificationConditionOperator) => {
    onChange(
      conditions.map((condition, i) => {
        if (i !== index) return condition;
        if (NO_VALUE_OPERATORS.has(operator)) {
          const next: NotificationCondition = { ...condition, operator };
          delete next.value;
          return next;
        }
        if (NUMERIC_OPERATORS.has(operator)) {
          const numeric = typeof condition.value === 'number' ? condition.value : Number(condition.value);
          return { ...condition, operator, value: Number.isFinite(numeric) ? numeric : undefined };
        }
        return { ...condition, operator };
      })
    );
  };

  return (
    <fieldset className={`${FORM_SECTION_CLASS} space-y-3`}>
      <legend className="text-sm font-medium text-foreground">{t('conditions')}</legend>
      {conditions.map((condition, index) => (
        <div key={index} className="grid gap-2 rounded-md border border-border bg-background/70 p-3 sm:grid-cols-[1fr_1fr_1fr_auto] sm:items-center">
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('conditionField')} help={t('help.conditionField')} required />
            <input
              aria-label="field"
              className={SMALL_FIELD_CLASS}
              value={condition.field}
              onChange={(event) => update(index, { field: event.target.value })}
              placeholder="booking.status"
            />
          </label>
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('conditionOperator')} help={t('help.conditionOperator')} required />
            <select
              aria-label="operator"
              className={SMALL_FIELD_CLASS}
              value={condition.operator}
              onChange={(event) => changeOperator(index, event.target.value as NotificationConditionOperator)}
            >
              {operators.map((operator) => (
                <option key={operator} value={operator}>
                  {operator}
                </option>
              ))}
            </select>
          </label>
          {NO_VALUE_OPERATORS.has(condition.operator) ? null : NUMERIC_OPERATORS.has(condition.operator) ? (
            <label className="space-y-1 text-xs">
              <HelpLabel label={t('conditionValue')} help={t('help.conditionValue')} required />
              <input
                aria-label="value"
                type="number"
                className={SMALL_FIELD_CLASS}
                value={typeof condition.value === 'number' && Number.isFinite(condition.value) ? condition.value : ''}
                onChange={(event) => {
                  const raw = event.target.value;
                  update(index, { value: raw === '' ? undefined : Number(raw) });
                }}
              />
            </label>
          ) : (
            <label className="space-y-1 text-xs">
              <HelpLabel label={t('conditionValue')} help={t('help.conditionValue')} required />
              <input
                aria-label="value"
                className={SMALL_FIELD_CLASS}
                value={LIST_OPERATORS.has(condition.operator) && Array.isArray(condition.value) ? condition.value.join(',') : (condition.value as string) ?? ''}
                onChange={(event) =>
                  update(index, {
                    value: LIST_OPERATORS.has(condition.operator)
                      ? event.target.value.split(',').map((item) => item.trim()).filter(Boolean)
                      : event.target.value,
                  })
                }
              />
            </label>
          )}
          <Button type="button" variant="ghost" size="sm" className="sm:self-end" onClick={() => onChange(conditions.filter((_, i) => i !== index))}>
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

  const updateSource = (index: number, source: NotificationVariableSpec['source']) => {
    onChange(
      variables.map((entry, i) => {
        if (i !== index) return entry;
        const spec: NotificationVariableSpec = { ...entry.spec, source };
        if (source === 'literal') {
          delete spec.path;
          delete spec.timezone_path;
        } else {
          delete spec.value;
        }
        return { ...entry, spec };
      })
    );
  };

  const updateTimezone = (index: number, timezone: string) => {
    onChange(
      variables.map((entry, i) => {
        if (i !== index) return entry;
        const spec: NotificationVariableSpec = { ...entry.spec, timezone: timezone || null };
        if (timezone) delete spec.timezone_path;
        return { ...entry, spec };
      })
    );
  };

  const updateTimezonePath = (index: number, timezonePath: string) => {
    onChange(
      variables.map((entry, i) => {
        if (i !== index) return entry;
        const spec: NotificationVariableSpec = { ...entry.spec, timezone_path: timezonePath || null };
        if (timezonePath) delete spec.timezone;
        return { ...entry, spec };
      })
    );
  };

  return (
    <fieldset className={`${FORM_SECTION_CLASS} space-y-3`}>
      <legend className="text-sm font-medium text-foreground">{t('variables')}</legend>
      {variables.map((entry, index) => (
        <div key={index} className="grid gap-2 rounded-md border border-border bg-background/70 p-3 sm:grid-cols-2">
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableKey')} help={t('help.variableKey')} required />
            <input
              aria-label="variable key"
              className={SMALL_FIELD_CLASS}
              value={entry.key}
              placeholder="customer_name"
              onChange={(event) => update(index, { key: event.target.value })}
            />
          </label>
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableSource')} help={t('help.variableSource')} required />
            <select
              aria-label="source"
              className={SMALL_FIELD_CLASS}
              value={entry.spec.source}
              onChange={(event) => updateSource(index, event.target.value as NotificationVariableSpec['source'])}
            >
              {sources.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </label>
          {entry.spec.source === 'literal' ? (
            <label className="space-y-1 text-xs">
              <HelpLabel label={t('variableValue')} help={t('help.variableValue')} required />
              <input
                aria-label="value"
                className={SMALL_FIELD_CLASS}
                value={(entry.spec.value as string) ?? ''}
                onChange={(event) => update(index, { value: event.target.value })}
                placeholder="value"
              />
            </label>
          ) : (
            <label className="space-y-1 text-xs">
              <HelpLabel label={t('variablePath')} help={t('help.variablePath')} required />
              <input
                aria-label="path"
                className={SMALL_FIELD_CLASS}
                value={entry.spec.path ?? ''}
                onChange={(event) => update(index, { path: event.target.value })}
                placeholder="booking.start_at"
              />
            </label>
          )}
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableFormat')} help={t('help.variableFormat')} />
            <select
              aria-label="format"
              className={SMALL_FIELD_CLASS}
              value={entry.spec.format ?? 'string'}
              onChange={(event) => update(index, { format: event.target.value as NotificationVariableSpec['format'] })}
            >
              {formats.map((format) => (
                <option key={format} value={format}>
                  {format}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableTimezone')} help={t('help.variableTimezone')} />
            <input
              aria-label="timezone"
              className={SMALL_FIELD_CLASS}
              value={entry.spec.timezone ?? ''}
              onChange={(event) => updateTimezone(index, event.target.value)}
              disabled={Boolean(entry.spec.timezone_path)}
              placeholder={tCommon('timezoneSuggestion')}
            />
          </label>
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableTimezonePath')} help={t('help.variableTimezonePath')} />
            <input
              aria-label="timezone path"
              className={SMALL_FIELD_CLASS}
              value={entry.spec.timezone_path ?? ''}
              onChange={(event) => updateTimezonePath(index, event.target.value)}
              disabled={Boolean(entry.spec.timezone)}
              placeholder="booking.timezone"
            />
          </label>
          <label className="space-y-1 text-xs">
            <HelpLabel label={t('variableDefault')} help={t('help.variableDefault')} />
            <input
              aria-label="default"
              className={SMALL_FIELD_CLASS}
              value={(entry.spec.default as string) ?? ''}
              onChange={(event) => update(index, { default: event.target.value || null })}
              placeholder={tCommon('defaultValue')}
            />
          </label>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <input
              id={`notification-variable-required-${index}`}
              type="checkbox"
              className="size-4 rounded border-border"
              checked={entry.spec.required ?? true}
              onChange={(event) => update(index, { required: event.target.checked })}
            />
            <label htmlFor={`notification-variable-required-${index}`}>{tCommon('required')}</label>
            <FieldHelp label={tCommon('required')} required={false}>{t('help.variableRequired')}</FieldHelp>
          </div>
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
