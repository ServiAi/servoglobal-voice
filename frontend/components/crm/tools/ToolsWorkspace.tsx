'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { Plus, ShieldAlert, Wrench } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CircularLoader } from '@/components/ui/circular-loader';
import {
  activateCustomToolAction,
  deleteCustomToolAction,
  disableCustomToolAction,
} from '@/app/[locale]/(tenant)/voice-ai/tools/actions';
import type { CustomToolGateState, CustomToolResponse } from '@/types/tools-custom';
import { CustomToolFormDialog } from './CustomToolFormDialog';
import { CustomToolTestPanel } from './CustomToolTestPanel';

type Props = {
  canEdit: boolean;
  initialTools: CustomToolResponse[];
  gateState: CustomToolGateState;
};

function endpointHost(baseUrl: string) {
  try {
    return new URL(baseUrl).host;
  } catch {
    return baseUrl;
  }
}

export function ToolsWorkspace({ canEdit, initialTools, gateState }: Props) {
  const t = useTranslations('crm.tools');
  const [tools, setTools] = useState(initialTools);
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<CustomToolResponse | null>(null);
  const [testing, setTesting] = useState<CustomToolResponse | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; code: string } | null>(null);

  const closeForm = () => {
    setCreating(false);
    setEditing(null);
  };

  const handleSaved = (tool: CustomToolResponse) => {
    setTools((current) => {
      const exists = current.some((item) => item.id === tool.id);
      return exists ? current.map((item) => (item.id === tool.id ? tool : item)) : [...current, tool];
    });
    closeForm();
  };

  const toggleStatus = async (tool: CustomToolResponse) => {
    setBusyId(tool.id);
    setRowError(null);
    const result =
      tool.status === 'active'
        ? await disableCustomToolAction(tool.id)
        : await activateCustomToolAction(tool.id);
    setBusyId(null);
    if (!result.ok) {
      setRowError({ id: tool.id, code: result.detail });
      return;
    }
    setTools((current) => current.map((item) => (item.id === tool.id ? result.data : item)));
  };

  const remove = async (tool: CustomToolResponse) => {
    setBusyId(tool.id);
    setRowError(null);
    const result = await deleteCustomToolAction(tool.id);
    setBusyId(null);
    if (!result.ok) {
      setRowError({ id: tool.id, code: result.status === 409 ? 'tool_in_use' : result.detail });
      return;
    }
    setTools((current) => current.filter((item) => item.id !== tool.id));
  };

  if (gateState !== 'ok') {
    const config = {
      feature_disabled: { title: t('featureDisabled.title'), description: t('featureDisabled.description') },
      access_denied: { title: t('accessDenied.title'), description: t('accessDenied.description') },
      error: { title: t('errors.loadTitle'), description: t('errors.generic') },
    }[gateState];
    return (
      <section className="relative overflow-hidden rounded-xl border border-border bg-card p-7 sm:p-10">
        <div className="relative max-w-xl">
          <span className="flex size-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <ShieldAlert className="size-5" aria-hidden="true" />
          </span>
          <h2 className="mt-5 text-xl font-bold text-foreground">{config.title}</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{config.description}</p>
        </div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
            <Wrench className="size-5" aria-hidden="true" />
          </span>
          <div>
            <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('description')}</p>
          </div>
        </div>
        {canEdit && (
          <Button type="button" className="gap-2 self-start sm:self-auto" onClick={() => setCreating(true)}>
            <Plus className="size-4" aria-hidden="true" />
            {t('new')}
          </Button>
        )}
      </div>

      {tools.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border bg-muted/20 p-8 text-center text-sm text-muted-foreground">
          {t('empty')}
        </div>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {tools.map((tool) => (
            <li
              key={tool.id}
              className="min-w-0 rounded-lg border border-border bg-background p-4 shadow-xs transition-colors hover:border-primary/25"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold text-foreground">{tool.name}</p>
                  <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{tool.key}</p>
                </div>
                <ToolStatusBadge status={tool.status} />
              </div>
              <p className="mt-2 line-clamp-2 text-sm text-muted-foreground">{tool.description}</p>
              <dl className="mt-4 grid grid-cols-2 gap-x-3 gap-y-2 border-y border-border py-3 text-xs text-muted-foreground">
                <dt>{t('columns.method')}</dt>
                <dd className="text-right font-medium text-foreground">{tool.method}</dd>
                <dt>{t('columns.endpoint')}</dt>
                <dd className="truncate text-right font-medium text-foreground">{endpointHost(tool.base_url)}</dd>
                <dt>{t('columns.auth')}</dt>
                <dd className="text-right font-medium text-foreground">{t(`auth.${tool.credential.auth_type}`)}</dd>
              </dl>
              <div className="mt-3 flex flex-col gap-2">
                <div className="flex flex-wrap items-center justify-end gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => setTesting(tool)}>
                    {t('actions.test')}
                  </Button>
                  {canEdit && (
                    <>
                      <Button type="button" variant="outline" size="sm" onClick={() => setEditing(tool)}>
                        {t('actions.edit')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={busyId === tool.id}
                        onClick={() => toggleStatus(tool)}
                      >
                        {busyId === tool.id && <CircularLoader size="xs" glow={false} />}
                        {tool.status === 'active' ? t('actions.disable') : t('actions.activate')}
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={busyId === tool.id}
                        onClick={() => remove(tool)}
                      >
                        {t('actions.delete')}
                      </Button>
                    </>
                  )}
                </div>
                {rowError?.id === tool.id && (
                  <p role="alert" className="text-right text-xs text-destructive">
                    {t(
                      rowError.code === 'tool_in_use'
                        ? 'errors.toolInUse'
                        : rowError.code === 'tool_credential_not_configured'
                          ? 'errors.credentialNotConfigured'
                          : 'errors.generic'
                    )}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {(creating || editing) && (
        <CustomToolFormDialog tool={editing} onClose={closeForm} onSaved={handleSaved} />
      )}
      {testing && <CustomToolTestPanel tool={testing} onClose={() => setTesting(null)} />}
    </div>
  );
}

function ToolStatusBadge({ status }: { status: CustomToolResponse['status'] }) {
  const t = useTranslations('crm.tools.status');
  return (
    <span
      className={`inline-flex min-h-7 items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
        status === 'active'
          ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
          : 'border-border bg-muted text-muted-foreground'
      }`}
    >
      {t(status)}
    </span>
  );
}
