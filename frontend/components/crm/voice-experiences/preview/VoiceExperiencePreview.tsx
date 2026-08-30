'use client';
/* eslint-disable @next/next/no-img-element */

import { useState } from 'react';
import { CheckCircle2, LockKeyhole, Mic2, PhoneCall, Sparkles, Zap } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { getPreCallVisibleContextFields } from '@/lib/voice-experiences/collection-modes';
import { isSafeHttpsUrl } from '@/lib/voice-experiences/url-safety';
import { resolveVoiceTheme } from '@/lib/voice-experiences/resolve-theme';
import type {
  VoiceContextFieldResponse,
  VoiceExperienceWriteRequest,
} from '@/types/voice-experiences';

type Props = {
  form: VoiceExperienceWriteRequest;
  contextFields: VoiceContextFieldResponse[];
  locale: string;
};

type PreviewState = 'form' | 'confirmation' | 'beforeCall';

function PreviewField({ field }: { field: VoiceContextFieldResponse }) {
  const inputClass =
    'mt-1.5 min-h-10 w-full rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-500 shadow-sm';
  if (field.field_type === 'textarea') {
    return <textarea disabled rows={2} className={`${inputClass} py-2`} />;
  }
  if (field.field_type === 'select') {
    return (
      <select disabled className={inputClass} defaultValue="">
        <option value="">—</option>
        {field.options_json.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }
  if (field.field_type === 'checkbox') {
    return <input type="checkbox" disabled className="mt-2 size-4 rounded border-slate-300" />;
  }
  return (
    <input
      disabled
      className={inputClass}
      type={field.field_type === 'integer' ? 'number' : field.field_type === 'phone' ? 'tel' : field.field_type}
    />
  );
}

export function VoiceExperiencePreview({ form, contextFields, locale }: Props) {
  const t = useTranslations('crm.voiceExperiences');
  const [state, setState] = useState<PreviewState>('form');
  const tokens = resolveVoiceTheme(form.theme);
  const accent = tokens.accent;
  const visibleFields = getPreCallVisibleContextFields(contextFields);
  const layoutClass =
    form.theme.layout === 'split'
      ? 'lg:grid-cols-[0.8fr_1.2fr]'
      : form.theme.layout === 'card'
        ? 'max-w-xl mx-auto'
        : 'max-w-2xl mx-auto';

  const states: PreviewState[] = ['form', 'confirmation', 'beforeCall'];

  const renderHeader = () => (
    <div className="space-y-4">
      {isSafeHttpsUrl(form.theme.logo_url) ? (
        <img
          src={form.theme.logo_url ?? undefined}
          alt=""
          className="h-10 max-w-40 object-contain object-left"
        />
      ) : (
        <span
          className="flex size-10 items-center justify-center rounded-lg text-white"
          style={{ backgroundColor: accent }}
        >
          <Mic2 className="size-5" aria-hidden="true" />
        </span>
      )}
      <div>
        <h2 className="text-2xl font-bold tracking-tight">{form.content.title}</h2>
        <p className="mt-2 text-sm leading-6" style={{ color: tokens.mutedFg }}>{form.content.description}</p>
      </div>
    </div>
  );

  return (
    <section
      data-testid="voice-experience-preview"
      className="relative overflow-hidden rounded-xl border border-slate-200 bg-slate-100 p-3 shadow-inner dark:border-slate-700 dark:bg-slate-950"
      aria-label={t('preview.label')}
    >
      <div className="mb-3 flex items-center justify-between gap-3 px-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
        <span className="inline-flex items-center gap-1.5">
          <Sparkles className="size-3.5" aria-hidden="true" />
          {t('preview.notFunctional')}
        </span>
        <span>{locale.toUpperCase()}</span>
      </div>

      <div
        role="tablist"
        aria-label={t('preview.states.label')}
        className="mb-3 flex flex-wrap gap-1.5 px-1"
      >
        {states.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={state === value}
            onClick={() => setState(value)}
            className={`rounded-full px-3 py-1 text-xs font-semibold transition ${
              state === value
                ? 'bg-slate-900 text-white dark:bg-white dark:text-slate-900'
                : 'bg-slate-200 text-slate-600 hover:bg-slate-300 dark:bg-slate-800 dark:text-slate-300'
            }`}
          >
            {t(`preview.states.${value}`)}
          </button>
        ))}
      </div>

      <div className="rounded-lg p-4 sm:p-6" style={{ backgroundColor: tokens.pageBg }}>
      <div
        role="tabpanel"
        className={`grid gap-6 rounded-lg p-5 shadow-lg sm:p-7 ${layoutClass}`}
        style={{ borderTop: `4px solid ${accent}`, backgroundColor: tokens.cardBg, color: tokens.fg }}
      >
        {state === 'form' ? (
          <>
            <div className="space-y-4">
              {renderHeader()}
            </div>

            <div className="space-y-3">
              {visibleFields.map((field) => (
                <label key={field.id} className="block text-xs font-semibold" style={{ color: tokens.fg }}>
                  {field.label}
                  {field.required ? <span className="ml-1 text-red-600">*</span> : null}
                  <PreviewField field={field} />
                </label>
              ))}
              {visibleFields.length === 0 ? (
                <p
                  className="rounded-md border border-dashed p-4 text-center text-xs"
                  style={{ borderColor: tokens.border, color: tokens.mutedFg }}
                >
                  {t('preview.noFields')}
                </p>
              ) : null}
              {form.consent.required ? (
                <label className="flex items-start gap-2 text-xs leading-5" style={{ color: tokens.mutedFg }}>
                  <input type="checkbox" disabled className="mt-0.5 size-4 rounded border-slate-300" />
                  <span>
                    {form.consent.label}
                    {isSafeHttpsUrl(form.consent.privacy_url) ? (
                      <a
                        href={form.consent.privacy_url ?? undefined}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="ml-1 underline"
                      >
                        {t('preview.privacy')}
                      </a>
                    ) : null}
                  </span>
                </label>
              ) : null}
              <button
                type="button"
                disabled
                className="min-h-11 w-full rounded-md px-4 text-sm font-bold text-white opacity-90"
                style={{ backgroundColor: accent }}
              >
                {form.content.submit_label}
              </button>
            </div>
          </>
        ) : null}

        {state === 'confirmation' ? (
          <div className="col-span-full mx-auto flex max-w-md flex-col items-center gap-4 py-6 text-center">
            <span
              className="flex size-12 items-center justify-center rounded-full text-white"
              style={{ backgroundColor: accent }}
            >
              <CheckCircle2 className="size-6" aria-hidden="true" />
            </span>
            <p className="text-lg font-bold">{form.content.success_message}</p>
            <p className="flex items-center gap-1.5 rounded-md px-3 py-2 text-xs" style={{ backgroundColor: tokens.headerTint, color: tokens.mutedFg }}>
              <CheckCircle2 className="size-3.5" aria-hidden="true" />
              {t('preview.confirmationRecorded')}
            </p>
            <button
              type="button"
              onClick={() => setState('beforeCall')}
              className="min-h-10 rounded-md border px-4 text-sm font-semibold hover:opacity-80"
              style={{ borderColor: tokens.border, color: tokens.fg }}
            >
              {t('preview.continueToCall')}
            </button>
          </div>
        ) : null}

        {state === 'beforeCall' ? (
          <div className="col-span-full mx-auto flex max-w-md flex-col items-center gap-4 py-6 text-center">
            {renderHeader()}
            {form.call_settings.show_microphone_help ? (
              <p className="flex items-start gap-2 rounded-md p-3 text-xs" style={{ backgroundColor: tokens.headerTint, color: tokens.mutedFg }}>
                <Mic2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {t('preview.microphoneHelp')}
              </p>
            ) : null}
            {form.call_settings.auto_start ? (
              <p className="flex items-start gap-2 rounded-md border border-dashed p-3 text-xs" style={{ borderColor: tokens.border, color: tokens.mutedFg }}>
                <Zap className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                {t('preview.autoStartActive')}
              </p>
            ) : (
              <button
                type="button"
                disabled
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md px-5 text-sm font-bold text-white opacity-90"
                style={{ backgroundColor: accent }}
              >
                <PhoneCall className="size-4" aria-hidden="true" />
                {form.content.call_label}
              </button>
            )}
          </div>
        ) : null}
      </div>
      </div>

      <p className="mt-3 flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
        <LockKeyhole className="size-3" aria-hidden="true" />
        {t('preview.localOnly')}
      </p>
    </section>
  );
}
