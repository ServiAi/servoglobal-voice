'use client';

import Link from 'next/link';
import type { useTranslations } from 'next-intl';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { AgentToolCatalogEntry, WhatsAppToolBindingConfig } from '@/types/agents';
import { AgentFieldLabel } from './AgentFieldLabel';
import { WhatsAppToolConfigurator } from './WhatsAppToolConfigurator';

const INTEGRATION_SETTINGS_PATH: Record<string, string> = {
  booking: 'integrations',
  whatsapp: 'integrations/whatsapp',
  crm: 'integrations',
  chatwoot: 'integrations/chatwoot',
};

export function AgentToolsSection({
  locale,
  catalog,
  bindings,
  disabled,
  onToggle,
  onConfigChange,
  t,
}: {
  locale: string;
  catalog: AgentToolCatalogEntry[];
  bindings: Record<string, { enabled: boolean; config: Record<string, unknown> }>;
  disabled: boolean;
  onToggle: (key: string, enabled: boolean) => void;
  onConfigChange: (key: string, config: Record<string, unknown>) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  // Only tools the platform can actually execute are ever offered here --
  // "planned" Registry entries (e.g. calendar.create_booking) never appear,
  // selectable or otherwise. See app.domain.tool_registry's docstring for
  // why: no fictional tools.
  const selectable = catalog.filter((tool) => tool.status === 'available');
  const platformTools = selectable.filter((tool) => tool.source === 'platform');
  const customTools = selectable.filter((tool) => tool.source === 'custom');

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('tools.title')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {platformTools.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('tools.empty')}</p>
          ) : (
            platformTools.map((tool) => (
              <ToolRow
                key={tool.key}
                locale={locale}
                tool={tool}
                checked={bindings[tool.key]?.enabled ?? false}
                config={bindings[tool.key]?.config ?? {}}
                disabled={disabled}
                onToggle={onToggle}
                onConfigChange={onConfigChange}
                t={t}
              >
                {!tool.available && tool.required_integration ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950">
                    <span>
                      {t('tools.requiresIntegration', {
                        integration: t(`tools.integration.${tool.required_integration}`),
                      })}
                    </span>
                    <Link
                      href={`/${locale}/${INTEGRATION_SETTINGS_PATH[tool.required_integration] ?? 'integrations'}`}
                      className="font-medium underline"
                    >
                      {t('tools.configureIntegration')}
                    </Link>
                  </div>
                ) : null}
              </ToolRow>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t('tools.customTitle')}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {customTools.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('tools.customEmpty')}</p>
          ) : (
            customTools.map((tool) => (
              <ToolRow
                key={tool.key}
                locale={locale}
                tool={tool}
                checked={bindings[tool.key]?.enabled ?? false}
                config={bindings[tool.key]?.config ?? {}}
                disabled={disabled}
                onToggle={onToggle}
                onConfigChange={onConfigChange}
                t={t}
              >
                {!tool.available ? (
                  <div className="mt-2 flex flex-wrap items-center gap-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-950">
                    <span>{t('tools.requiresCredential')}</span>
                    <Link href={`/${locale}/voice-ai/tools`} className="font-medium underline">
                      {t('tools.configureCredential')}
                    </Link>
                  </div>
                ) : null}
              </ToolRow>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Platform Tool contract, rendered read-only: what the model decides
 * (llm_input_schema properties), what ServiGlobal resolves automatically
 * from SessionContextV1 (context_requirements), and -- only when the tool
 * actually has one -- an editable configuration section. Custom tools
 * never have context_requirements/binding_config_schema (see
 * ResolvedToolDefinition's docstring), so this section is a no-op for them. */
function ToolContract({ tool, t }: { tool: AgentToolCatalogEntry; t: ReturnType<typeof useTranslations> }) {
  const llmProperties = Object.keys((tool.input_schema.properties as Record<string, unknown> | undefined) ?? {});
  return (
    <div className="mt-2 grid gap-2 text-xs text-muted-foreground sm:grid-cols-2">
      <div>
        <p className="font-medium text-foreground">{t('tools.llmInputsTitle')}</p>
        {tool.configuration_required ? (
          <p>{t('tools.llmInputsDependOnConfig')}</p>
        ) : llmProperties.length === 0 ? (
          <p>{t('tools.noLlmInputs')}</p>
        ) : (
          <ul className="list-inside list-disc">
            {llmProperties.map((key) => (
              <li key={key}>{key}</li>
            ))}
          </ul>
        )}
      </div>
      <div>
        <p className="font-medium text-foreground">{t('tools.contextAutoTitle')}</p>
        {tool.context_requirements.length === 0 ? (
          <p>{t('tools.noContext')}</p>
        ) : (
          <ul className="list-inside list-disc">
            {tool.context_requirements.map((req) => (
              <li key={req.path}>{req.path}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ToolRow({
  locale,
  tool,
  checked,
  config,
  disabled,
  onToggle,
  onConfigChange,
  t,
  children,
}: {
  locale: string;
  tool: AgentToolCatalogEntry;
  checked: boolean;
  config: Record<string, unknown>;
  disabled: boolean;
  onToggle: (key: string, enabled: boolean) => void;
  onConfigChange: (key: string, config: Record<string, unknown>) => void;
  t: ReturnType<typeof useTranslations>;
  children?: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border p-3">
      <div className="flex items-start gap-2.5 text-sm">
        <input
          id={`agent-tool-${tool.key}`}
          type="checkbox"
          className="mt-0.5 size-4 rounded border-input"
          checked={checked}
          disabled={disabled || !tool.available}
          onChange={(e) => onToggle(tool.key, e.target.checked)}
        />
        <span className="flex-1">
          <span className="flex items-center gap-1.5">
            <label htmlFor={`agent-tool-${tool.key}`} className="font-medium text-foreground">
              {tool.name}
            </label>
            <AgentFieldLabel label={tool.name} help={tool.description} showLabel={false} />
          </span>
          <span className="block text-muted-foreground">{tool.description}</span>
        </span>
      </div>
      {children}
      {tool.source === 'platform' ? <ToolContract tool={tool} t={t} /> : null}
      {checked && tool.key === 'whatsapp.send_message' ? (
        <WhatsAppToolConfigurator
          locale={locale}
          config={config}
          disabled={disabled}
          onChange={(next) => onConfigChange(tool.key, next as unknown as WhatsAppToolBindingConfig & Record<string, unknown>)}
          t={t}
        />
      ) : null}
    </div>
  );
}
