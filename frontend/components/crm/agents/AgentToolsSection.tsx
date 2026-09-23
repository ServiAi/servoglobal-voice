'use client';

import Link from 'next/link';
import type { useTranslations } from 'next-intl';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { AgentToolCatalogEntry } from '@/types/agents';
import { AgentFieldLabel } from './AgentFieldLabel';

const INTEGRATION_SETTINGS_PATH: Record<string, string> = {
  booking: 'integrations',
  whatsapp: 'integrations/whatsapp',
  crm: 'integrations',
  chatwoot: 'integrations/chatwoot',
};

export function AgentToolsSection({
  locale,
  catalog,
  enabledKeys,
  disabled,
  onToggle,
  t,
}: {
  locale: string;
  catalog: AgentToolCatalogEntry[];
  enabledKeys: string[];
  disabled: boolean;
  onToggle: (key: string, enabled: boolean) => void;
  t: ReturnType<typeof useTranslations>;
}) {
  // Only tools the platform can actually execute are ever offered here --
  // "planned" Registry entries (e.g. calendar.create_booking) never appear,
  // selectable or otherwise. See app.domain.tool_registry's docstring for
  // why: no fictional tools.
  const selectable = catalog.filter((tool) => tool.status === 'available');
  const enabled = new Set(enabledKeys);
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
                tool={tool}
                checked={enabled.has(tool.key)}
                disabled={disabled}
                onToggle={onToggle}
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
                tool={tool}
                checked={enabled.has(tool.key)}
                disabled={disabled}
                onToggle={onToggle}
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

function ToolRow({
  tool,
  checked,
  disabled,
  onToggle,
  children,
}: {
  tool: AgentToolCatalogEntry;
  checked: boolean;
  disabled: boolean;
  onToggle: (key: string, enabled: boolean) => void;
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
        <span>
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
    </div>
  );
}
