'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import type { useTranslations } from 'next-intl';
import { fetchApprovedWhatsAppTemplatesAction } from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import {
  WHATSAPP_ALLOWED_CONTEXT_PATHS,
  type WhatsAppRecipientStrategy,
  type WhatsAppToolBindingConfig,
  type WhatsAppVariableMapping,
  type WhatsAppVariableSource,
} from '@/types/agents';
import type { WhatsAppTemplateResponse } from '@/types/crm';

const EMPTY_CONFIG: WhatsAppToolBindingConfig = {
  contract_version: 2,
  template_key: '',
  recipient: { strategy: 'contact_then_caller' },
  variables: {},
};

const RECIPIENT_STRATEGIES: WhatsAppRecipientStrategy[] = ['contact_then_caller', 'contact', 'caller'];
const VARIABLE_SOURCES: WhatsAppVariableSource[] = ['llm', 'context', 'fixed'];

function asWhatsAppConfig(config: Record<string, unknown> | undefined): WhatsAppToolBindingConfig {
  if (config && config.contract_version === 2 && typeof config.template_key === 'string') {
    return config as unknown as WhatsAppToolBindingConfig;
  }
  return EMPTY_CONFIG;
}

function templateVariableKeys(template: WhatsAppTemplateResponse | null): string[] {
  const parameters = template?.variables?.parameters;
  if (!Array.isArray(parameters)) return [];
  return parameters
    .map((item) => (item && typeof item === 'object' && 'key' in item ? String((item as { key: unknown }).key) : null))
    .filter((key): key is string => key !== null);
}

export function WhatsAppToolConfigurator({
  locale,
  config,
  disabled,
  onChange,
  t,
}: {
  locale: string;
  config: Record<string, unknown> | undefined;
  disabled: boolean;
  onChange: (config: WhatsAppToolBindingConfig) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  const [templates, setTemplates] = useState<WhatsAppTemplateResponse[] | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetchApprovedWhatsAppTemplatesAction().then((result) => {
      if (cancelled) return;
      if (result.ok) setTemplates(result.data);
      else setLoadFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = asWhatsAppConfig(config);
  const selectedTemplate = templates?.find((tpl) => tpl.template_key === value.template_key) ?? null;
  const variableKeys = templateVariableKeys(selectedTemplate);

  function handleTemplateChange(templateKey: string) {
    const template = templates?.find((tpl) => tpl.template_key === templateKey) ?? null;
    const keys = templateVariableKeys(template);
    const variables: Record<string, WhatsAppVariableMapping> = {};
    for (const key of keys) {
      variables[key] = value.variables[key] ?? { source: 'llm', type: 'string', description: '' };
    }
    onChange({ ...value, template_key: templateKey, variables });
  }

  function handleRecipientChange(strategy: WhatsAppRecipientStrategy) {
    onChange({ ...value, recipient: { strategy } });
  }

  function handleVariableSourceChange(key: string, source: WhatsAppVariableSource) {
    const mapping: WhatsAppVariableMapping =
      source === 'llm'
        ? { source: 'llm', type: 'string', description: '' }
        : source === 'context'
          ? { source: 'context', path: WHATSAPP_ALLOWED_CONTEXT_PATHS[0] }
          : { source: 'fixed', value: '' };
    onChange({ ...value, variables: { ...value.variables, [key]: mapping } });
  }

  function handleVariableFieldChange(key: string, patch: Partial<WhatsAppVariableMapping>) {
    const current = value.variables[key];
    if (!current) return;
    onChange({ ...value, variables: { ...value.variables, [key]: { ...current, ...patch } as WhatsAppVariableMapping } });
  }

  const selectClass =
    'min-h-10 w-full rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-muted disabled:text-muted-foreground';

  return (
    <div className="mt-3 space-y-4 rounded-md border border-border bg-muted/30 p-3">
      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">{t('tools.whatsapp.template')}</span>
        {templates === null && !loadFailed ? (
          <p className="text-xs text-muted-foreground">…</p>
        ) : loadFailed ? (
          <p className="text-xs text-destructive">{t('tools.whatsapp.templatesLoadError')}</p>
        ) : (templates ?? []).length === 0 ? (
          <p className="text-xs text-muted-foreground">
            {t('tools.whatsapp.noTemplates')}{' '}
            <Link href={`/${locale}/integrations/whatsapp`} className="font-medium underline">
              {t('tools.whatsapp.manageTemplates')}
            </Link>
          </p>
        ) : (
          <select
            className={selectClass}
            disabled={disabled}
            value={value.template_key}
            onChange={(e) => handleTemplateChange(e.target.value)}
          >
            <option value="">{t('tools.whatsapp.templatePlaceholder')}</option>
            {(templates ?? []).map((tpl) => (
              <option key={tpl.template_key} value={tpl.template_key}>
                {tpl.name}
              </option>
            ))}
          </select>
        )}
      </label>

      <label className="flex flex-col gap-1.5 text-sm">
        <span className="font-medium text-foreground">{t('tools.whatsapp.recipient')}</span>
        <select
          className={selectClass}
          disabled={disabled}
          value={value.recipient.strategy}
          onChange={(e) => handleRecipientChange(e.target.value as WhatsAppRecipientStrategy)}
        >
          {RECIPIENT_STRATEGIES.map((strategy) => (
            <option key={strategy} value={strategy}>
              {t(`tools.whatsapp.recipientStrategy.${strategy}`)}
            </option>
          ))}
        </select>
      </label>

      {value.template_key ? (
        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium text-foreground">{t('tools.whatsapp.variablesTitle')}</span>
          {variableKeys.map((key) => {
            const mapping = value.variables[key];
            return (
              <div key={key} className="grid gap-2 rounded-md border border-border bg-background p-2.5 sm:grid-cols-[1fr_1fr_1fr]">
                <span className="self-center text-sm font-medium text-foreground">{key}</span>
                <select
                  className={selectClass}
                  disabled={disabled}
                  value={mapping?.source ?? 'llm'}
                  onChange={(e) => handleVariableSourceChange(key, e.target.value as WhatsAppVariableSource)}
                >
                  {VARIABLE_SOURCES.map((source) => (
                    <option key={source} value={source}>
                      {t(`tools.whatsapp.variableSource.${source}`)}
                    </option>
                  ))}
                </select>
                {mapping?.source === 'context' ? (
                  <select
                    className={selectClass}
                    disabled={disabled}
                    value={mapping.path}
                    onChange={(e) => handleVariableFieldChange(key, { path: e.target.value })}
                  >
                    {WHATSAPP_ALLOWED_CONTEXT_PATHS.map((path) => (
                      <option key={path} value={path}>
                        {path}
                      </option>
                    ))}
                  </select>
                ) : mapping?.source === 'fixed' ? (
                  <input
                    className={selectClass}
                    disabled={disabled}
                    value={mapping.value}
                    placeholder={t('tools.whatsapp.variableFixedValuePlaceholder')}
                    onChange={(e) => handleVariableFieldChange(key, { value: e.target.value })}
                  />
                ) : (
                  <input
                    className={selectClass}
                    disabled={disabled}
                    value={mapping?.source === 'llm' ? (mapping.description ?? '') : ''}
                    placeholder={t('tools.whatsapp.variableDescriptionPlaceholder')}
                    onChange={(e) => handleVariableFieldChange(key, { description: e.target.value })}
                  />
                )}
              </div>
            );
          })}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">{t('tools.whatsapp.selectTemplateFirst')}</p>
      )}
    </div>
  );
}
