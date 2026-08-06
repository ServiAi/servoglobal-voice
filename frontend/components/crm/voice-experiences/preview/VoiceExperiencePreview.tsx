'use client';
/* eslint-disable @next/next/no-img-element */

import { LockKeyhole, Mic2, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { isSafeHttpsUrl } from '@/lib/voice-experiences/url-safety';
import type {
  VoiceContextFieldResponse,
  VoiceExperienceWriteRequest,
} from '@/types/voice-experiences';

type Props = {
  form: VoiceExperienceWriteRequest;
  contextFields: VoiceContextFieldResponse[];
  locale: string;
};

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
  const accent = form.theme.primary_color ?? '#0891B2';
  const visibleFields = [...contextFields]
    .filter((field) => field.collection_mode !== 'internal_only')
    .sort((a, b) => a.position - b.position);
  const layoutClass =
    form.theme.layout === 'split'
      ? 'lg:grid-cols-[0.8fr_1.2fr]'
      : form.theme.layout === 'card'
        ? 'max-w-xl mx-auto'
        : 'max-w-2xl mx-auto';

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
        className={`grid gap-6 rounded-lg bg-white p-5 text-slate-950 shadow-lg sm:p-7 ${layoutClass}`}
        style={{ borderTop: `4px solid ${accent}` }}
      >
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
            <p className="mt-2 text-sm leading-6 text-slate-600">{form.content.description}</p>
          </div>
          {form.call_settings.show_microphone_help ? (
            <p className="flex items-start gap-2 rounded-md bg-slate-100 p-3 text-xs text-slate-600">
              <Mic2 className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              {t('preview.microphoneHelp')}
            </p>
          ) : null}
        </div>

        <div className="space-y-3">
          {visibleFields.map((field) => (
            <label key={field.id} className="block text-xs font-semibold text-slate-700">
              {field.label}
              {field.required ? <span className="ml-1 text-red-600">*</span> : null}
              <PreviewField field={field} />
            </label>
          ))}
          {visibleFields.length === 0 ? (
            <p className="rounded-md border border-dashed border-slate-300 p-4 text-center text-xs text-slate-500">
              {t('preview.noFields')}
            </p>
          ) : null}
          {form.consent.required ? (
            <label className="flex items-start gap-2 text-xs leading-5 text-slate-600">
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
          <p className="flex items-center justify-center gap-1.5 text-[11px] text-slate-400">
            <LockKeyhole className="size-3" aria-hidden="true" />
            {t('preview.localOnly')}
          </p>
        </div>
      </div>
    </section>
  );
}
