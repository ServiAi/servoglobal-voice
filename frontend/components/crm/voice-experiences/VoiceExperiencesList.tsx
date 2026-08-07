'use client';

import { useState, useTransition } from 'react';
import Link from 'next/link';
import {
  Archive,
  ArrowRight,
  Cable,
  CircleOff,
  Clock3,
  Lock,
  Mic2,
  Plus,
  RadioTower,
  ShieldAlert,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  archiveVoiceExperienceAction,
  deleteVoiceExperienceAction,
} from '@/app/[locale]/crm/settings/voice-experiences/actions';
import { getVoiceExperienceErrorKey } from '@/lib/voice-experiences/error-messages';
import { ActionDialog } from './ActionDialog';
import { VoiceExperienceStatusBadge } from './VoiceExperienceStatusBadge';
import { Button } from '@/components/ui/button';
import type { VoiceAgentConfigResponse } from '@/types/crm';
import type {
  VoiceExperienceGateState,
  VoiceExperienceResponse,
} from '@/types/voice-experiences';

type Props = {
  locale: string;
  canEdit: boolean;
  initialExperiences: VoiceExperienceResponse[];
  agents: VoiceAgentConfigResponse[];
  versionCounts: Record<string, number>;
  gateState: VoiceExperienceGateState;
};

export function VoiceExperiencesList({
  locale,
  canEdit,
  initialExperiences,
  agents,
  versionCounts,
  gateState,
}: Props) {
  const t = useTranslations('crm.voiceExperiences');
  const [experiences, setExperiences] = useState(initialExperiences);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const agentNames = new Map(agents.map((agent) => [agent.id, agent.display_name]));

  const mutate = (
    experienceId: string,
    action: (locale: string, id: string) => Promise<
      | { ok: true; data: VoiceExperienceResponse }
      | { ok: false; status: number; detail: string }
    >
  ) => {
    startTransition(async () => {
      setError(null);
      const result = await action(locale, experienceId);
      if (!result.ok) {
        const key = result.status === 409 ? 'conflict' : result.status === 422 ? 'validation' : 'generic';
        setError(t(`errors.${key}`));
        return;
      }
      setExperiences((current) =>
        current.map((experience) =>
          experience.id === result.data.id ? result.data : experience
        )
      );
    });
  };

  const remove = (experienceId: string) => {
    startTransition(async () => {
      setError(null);
      const result = await deleteVoiceExperienceAction(locale, experienceId);
      if (!result.ok) {
        const backendKey = getVoiceExperienceErrorKey(result.detail);
        if ((result.status === 409 || result.status === 422) && backendKey) {
          setError(t(`errors.backend.${backendKey}`));
          return;
        }
        const key = result.status === 409 ? 'conflict' : result.status === 422 ? 'validation' : 'generic';
        setError(t(`errors.${key}`));
        return;
      }
      setExperiences((current) => current.filter((experience) => experience.id !== experienceId));
    });
  };

  if (gateState !== 'ok') {
    const config = {
      feature_disabled: {
        icon: CircleOff,
        title: t('featureDisabled.title'),
        description: t('featureDisabled.description'),
      },
      integration_disabled: {
        icon: Cable,
        title: t('integrationDisabled.title'),
        description: t('integrationDisabled.description'),
      },
      no_agents: {
        icon: Mic2,
        title: t('noAgents.title'),
        description: t('noAgents.description'),
      },
      access_denied: {
        icon: ShieldAlert,
        title: t('accessDenied.title'),
        description: t('accessDenied.description'),
      },
      error: {
        icon: ShieldAlert,
        title: t('errors.loadTitle'),
        description: t('errors.generic'),
      },
    }[gateState];
    const Icon = config.icon;
    return (
      <section className="relative overflow-hidden rounded-xl border border-border bg-card p-7 sm:p-10">
        <div className="absolute inset-y-0 right-0 w-1/3 bg-[radial-gradient(circle_at_center,hsl(var(--primary)/0.12),transparent_70%)]" />
        <div className="relative max-w-xl">
          <span className="flex size-11 items-center justify-center rounded-lg bg-muted text-muted-foreground">
            <Icon className="size-5" aria-hidden="true" />
          </span>
          <h2 className="mt-5 text-xl font-bold text-foreground">{config.title}</h2>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{config.description}</p>
          {gateState === 'integration_disabled' || gateState === 'no_agents' ? (
            <Button asChild className="mt-5">
              <Link href={`/${locale}/crm/settings/integrations`}>
                {t(gateState === 'no_agents' ? 'noAgents.cta' : 'integrationDisabled.cta')}
                <ArrowRight className="ml-2 size-4" aria-hidden="true" />
              </Link>
            </Button>
          ) : null}
        </div>
      </section>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-primary">
            {t('list.eyebrow')}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t('list.count', { count: experiences.length })}
          </p>
        </div>
        {canEdit ? (
          <Button asChild>
            <Link href={`/${locale}/crm/settings/voice-experiences/new`}>
              <Plus className="mr-2 size-4" aria-hidden="true" />
              {t('newExperience')}
            </Link>
          </Button>
        ) : null}
      </div>

      <p className="flex items-start gap-2 rounded-lg border border-border bg-muted/40 p-3 text-xs leading-5 text-muted-foreground">
        <Lock className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
        {t('list.privateNotice')}
      </p>

      <div aria-live="polite">
        {error ? (
          <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </div>

      {experiences.length === 0 ? (
        <section className="grid min-h-72 place-items-center rounded-xl border border-dashed border-border bg-muted/[0.18] p-8 text-center">
          <div className="max-w-md">
            <span className="mx-auto flex size-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <Sparkles className="size-6" aria-hidden="true" />
            </span>
            <h2 className="mt-5 text-lg font-bold text-foreground">{t('list.empty')}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t('list.emptyAction')}</p>
            {canEdit ? (
              <Button asChild className="mt-5">
                <Link href={`/${locale}/crm/settings/voice-experiences/new`}>
                  <Plus className="mr-2 size-4" aria-hidden="true" />
                  {t('newExperience')}
                </Link>
              </Button>
            ) : null}
          </div>
        </section>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {experiences.map((experience) => {
            const versions = versionCounts[experience.id] ?? 0;
            return (
              <article
                key={experience.id}
                className="group relative flex min-h-72 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-sm transition hover:-translate-y-0.5 hover:border-primary/35 hover:shadow-md"
              >
                <div className="h-1 w-full bg-gradient-to-r from-cyan-500 via-primary to-amber-400 opacity-70" />
                <div className="flex flex-1 flex-col p-5">
                  <div className="flex items-start justify-between gap-3">
                    <span className="flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Mic2 className="size-5" aria-hidden="true" />
                    </span>
                    <VoiceExperienceStatusBadge status={experience.status} />
                  </div>
                  <h2 className="mt-4 line-clamp-2 text-lg font-bold tracking-tight text-foreground">
                    {experience.name}
                  </h2>
                  <p className="mt-1 truncate text-sm text-muted-foreground">
                    {agentNames.get(experience.agent_config_id) ?? t('list.unknownAgent')}
                  </p>
                  <dl className="mt-5 grid grid-cols-2 gap-3 text-xs">
                    <div className="rounded-md bg-muted/45 p-2.5">
                      <dt className="text-muted-foreground">{t('list.locale')}</dt>
                      <dd className="mt-1 font-semibold uppercase text-foreground">
                        {experience.default_locale}
                      </dd>
                    </div>
                    <div className="rounded-md bg-muted/45 p-2.5">
                      <dt className="text-muted-foreground">{t('list.versions')}</dt>
                      <dd className="mt-1 flex items-center gap-1 font-semibold text-foreground">
                        <RadioTower className="size-3.5" aria-hidden="true" />
                        {versions}
                      </dd>
                    </div>
                  </dl>
                  <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
                    <Clock3 className="size-3.5" aria-hidden="true" />
                    {t('list.updated', {
                      date: new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(
                        new Date(experience.updated_at)
                      ),
                    })}
                  </p>
                  <div className="mt-auto flex flex-wrap items-center gap-2 pt-5">
                    <Button asChild size="sm" variant="outline" className="mr-auto">
                      <Link href={`/${locale}/crm/settings/voice-experiences/${experience.id}`}>
                        {t('list.open')}
                        <ArrowRight className="ml-1.5 size-4" aria-hidden="true" />
                      </Link>
                    </Button>
                    {canEdit && experience.status !== 'published' && experience.status !== 'archived' ? (
                      <ActionDialog
                        trigger={
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            disabled={isPending}
                            aria-label={t('actions.archive')}
                          >
                            <Archive className="size-4" aria-hidden="true" />
                          </Button>
                        }
                        title={t('confirm.archive.title')}
                        description={t('confirm.archive.description')}
                        confirmLabel={t('actions.archive')}
                        cancelLabel={t('common.cancel')}
                        destructive
                        busy={isPending}
                        onConfirm={() => mutate(experience.id, archiveVoiceExperienceAction)}
                      />
                    ) : null}
                    {canEdit && experience.status === 'archived' && versions === 0 ? (
                      <ActionDialog
                        trigger={
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            disabled={isPending}
                            aria-label={t('actions.delete')}
                          >
                            <Trash2 className="size-4" aria-hidden="true" />
                          </Button>
                        }
                        title={t('confirm.delete.title')}
                        description={t('confirm.delete.description')}
                        confirmLabel={t('actions.delete')}
                        cancelLabel={t('common.cancel')}
                        destructive
                        busy={isPending}
                        onConfirm={() => remove(experience.id)}
                      />
                    ) : null}
                    {canEdit && experience.status === 'archived' && versions > 0 ? (
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        disabled
                        aria-label={t('errors.backend.deleteHistoryBlocked')}
                        title={t('errors.backend.deleteHistoryBlocked')}
                      >
                        <Lock className="size-4" aria-hidden="true" />
                      </Button>
                    ) : null}
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
