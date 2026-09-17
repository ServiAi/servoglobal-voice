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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('tools.title')}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {selectable.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t('tools.empty')}</p>
        ) : (
          selectable.map((tool) => (
            <div key={tool.key} className="rounded-lg border border-border p-3">
              <div className="flex items-start gap-2.5 text-sm">
                <input
                  id={`agent-tool-${tool.key}`}
                  type="checkbox"
                  className="mt-0.5 size-4 rounded border-input"
                  checked={enabled.has(tool.key)}
                  disabled={disabled || !tool.available}
                  onChange={(e) => onToggle(tool.key, e.target.checked)}
                />
                <span>
                  <span className="flex items-center gap-1.5">
                    <label htmlFor={`agent-tool-${tool.key}`} className="font-medium text-foreground">{tool.name}</label>
                    <AgentFieldLabel label={tool.name} help={tool.description} showLabel={false} />
                  </span>
                  <span className="block text-muted-foreground">{tool.description}</span>
                </span>
              </div>
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
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
