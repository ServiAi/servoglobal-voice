'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import { ArrowRight, Bot, Clock3, Plus, RotateCcw, ShieldAlert, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { archiveAgentAction } from '@/app/[locale]/(tenant)/voice-ai/agents/actions';
import { ActionDialog } from '@/components/crm/voice-experiences/ActionDialog';
import { Button } from '@/components/ui/button';
import { AgentStatusBadge } from './AgentStatusBadge';
import type { AgentGateState, AgentResponse } from '@/types/agents';

type Props = {
  locale: string;
  canEdit: boolean;
  initialAgents: AgentResponse[];
  gateState: AgentGateState;
};

export function AgentsList({ locale, canEdit, initialAgents, gateState }: Props) {
  const t = useTranslations('crm.agentBuilder');
  const [agents, setAgents] = useState(initialAgents);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const archive = (agentId: string) => {
    startTransition(async () => {
      setError(null);
      const result = await archiveAgentAction(locale, agentId);
      if (!result.ok) {
        setError(t(result.status === 409 ? 'errors.conflict' : 'errors.generic'));
        return;
      }
      setAgents((current) =>
        current.map((agent) => (agent.id === result.data.id ? result.data : agent))
      );
    });
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
    <div className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">{t('list.eyebrow')}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t('list.count', { count: agents.length })}</p>
        </div>
        {canEdit ? (
          <Button asChild>
            <Link href={`/${locale}/voice-ai/agents/new`}>
              <Plus className="mr-2 size-4" aria-hidden="true" />
              {t('newAgent')}
            </Link>
          </Button>
        ) : null}
      </div>

      <div aria-live="polite">
        {error ? (
          <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>

      {agents.length === 0 ? (
        <section className="grid min-h-72 place-items-center rounded-xl border border-dashed border-border bg-muted/[0.18] p-8 text-center">
          <div className="max-w-md">
            <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Sparkles className="size-6" aria-hidden="true" />
            </span>
            <h2 className="mt-5 text-lg font-bold text-foreground">{t('list.empty')}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('list.emptyAction')}</p>
            {canEdit ? (
              <Button asChild className="mt-5">
                <Link href={`/${locale}/voice-ai/agents/new`}>
                  <Plus className="mr-2 size-4" aria-hidden="true" />
                  {t('newAgent')}
                </Link>
              </Button>
            ) : null}
          </div>
        </section>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <article
              key={agent.id}
              className="group relative flex min-h-56 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md"
            >
              <div className="h-1 w-full bg-gradient-to-r from-cyan-500 via-primary to-amber-400 opacity-70" />
              <div className="flex flex-1 flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Bot className="size-5" aria-hidden="true" />
                  </span>
                  <AgentStatusBadge status={agent.status} />
                </div>
                <h2 className="mt-4 line-clamp-2 text-lg font-bold tracking-tight text-foreground">
                  {agent.name}
                </h2>
                <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                  {agent.description || t('list.noDescription')}
                </p>
                <p className="mt-4 text-xs text-muted-foreground">
                  {t('list.engine')}: <span className="font-semibold text-foreground">Ultravox</span>
                </p>
                <p className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Clock3 className="size-3.5" aria-hidden="true" />
                  {t('list.updated', {
                    date: new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(
                      new Date(agent.updated_at)
                    ),
                  })}
                </p>
                <div className="mt-auto flex flex-wrap items-center gap-2 pt-5">
                  <Button asChild size="sm" variant="outline" className="mr-auto">
                    <Link href={`/${locale}/voice-ai/agents/${agent.id}`}>
                      {t('list.open')}
                      <ArrowRight className="ml-1.5 size-4" aria-hidden="true" />
                    </Link>
                  </Button>
                  {canEdit && agent.status !== 'archived' ? (
                    <ActionDialog
                      trigger={
                        <Button type="button" size="sm" variant="ghost" disabled={isPending}>
                          {t('actions.archive')}
                        </Button>
                      }
                      title={t('confirm.archive.title')}
                      description={t('confirm.archive.description')}
                      confirmLabel={t('actions.archive')}
                      cancelLabel={t('common.cancel')}
                      destructive
                      busy={isPending}
                      onConfirm={() => archive(agent.id)}
                    />
                  ) : null}
                  {agent.status === 'archived' ? (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                      <RotateCcw className="size-3.5" aria-hidden="true" />
                      {t('list.archivedNotice')}
                    </span>
                  ) : null}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
