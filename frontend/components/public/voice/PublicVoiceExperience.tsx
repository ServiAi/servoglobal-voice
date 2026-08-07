import type { CSSProperties, ReactNode } from 'react';
import { Check, LockKeyhole, ShieldCheck } from 'lucide-react';

import { isSafeHttpsUrl } from '@/lib/voice-experiences/url-safety';
import type {
  PublicVoiceContextField,
  PublicVoiceExperience as PublicVoiceExperienceData,
} from '@/types/public-voice-experiences';

export interface PublicVoiceMessages {
  eyebrow: string;
  version: string;
  required: string;
  selectPlaceholder: string;
  privacy: string;
  emptyFields: string;
  noticeTitle: string;
  noticeDescription: string;
  logoAlt: string;
}

interface Props {
  experience: PublicVoiceExperienceData;
  messages: PublicVoiceMessages;
}

function FieldControl({ field, placeholder }: { field: PublicVoiceContextField; placeholder: string }) {
  const common = {
    disabled: true,
    id: `public-field-${field.key}`,
    name: field.key,
    required: field.required,
    className:
      'mt-2 min-h-11 w-full rounded-xl border border-slate-200 bg-slate-50 px-3.5 text-sm text-slate-600 disabled:cursor-not-allowed disabled:opacity-100',
  };

  if (field.field_type === 'textarea') return <textarea {...common} rows={3} />;

  if (field.field_type === 'select') {
    return (
      <select {...common} defaultValue="">
        <option value="">{placeholder}</option>
        {field.options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    );
  }

  if (field.field_type === 'checkbox') {
    return (
      <span className="mt-2 flex min-h-11 items-center gap-3 rounded-xl border border-slate-200 bg-slate-50 px-3.5 text-sm text-slate-600">
        <input {...common} className="size-4 accent-current" type="checkbox" />
        <span>{field.description || field.label}</span>
      </span>
    );
  }

  const type = {
    date: 'date',
    email: 'email',
    integer: 'number',
    phone: 'tel',
    text: 'text',
  }[field.field_type];

  return <input {...common} type={type} />;
}

function Shell({ children, layout }: { children: ReactNode; layout: PublicVoiceExperienceData['theme']['layout'] }) {
  return (
    <main
      className={`min-h-screen px-4 py-10 sm:px-6 sm:py-16 ${layout === 'split' ? 'lg:grid lg:place-items-center' : ''}`}
      data-testid="public-voice-runtime"
    >
      {children}
    </main>
  );
}

export function PublicVoiceExperience({ experience, messages }: Props) {
  const safeLogo = isSafeHttpsUrl(experience.theme.logo_url) ? experience.theme.logo_url : null;
  const safePrivacy = isSafeHttpsUrl(experience.consent.privacy_url) ? experience.consent.privacy_url : null;
  const accent = experience.theme.primary_color || '#0f766e';
  const style = { '--voice-accent': accent, backgroundColor: '#f4f7f6' } as CSSProperties;
  const isSplit = experience.theme.layout === 'split';

  return (
    <div style={style} className="min-h-screen text-slate-950">
      <Shell layout={experience.theme.layout}>
        <section
          className={`mx-auto overflow-hidden border border-black/10 bg-white shadow-[0_24px_80px_-36px_rgba(15,23,42,0.38)] ${
            isSplit ? 'max-w-5xl rounded-[2rem] lg:grid lg:grid-cols-[0.78fr_1.22fr]' : 'max-w-2xl rounded-[2rem]'
          }`}
        >
          <header
            className={`relative overflow-hidden px-6 py-8 sm:px-10 ${isSplit ? 'lg:flex lg:min-h-[620px] lg:flex-col lg:justify-between lg:py-12' : ''}`}
            style={{ backgroundColor: 'color-mix(in srgb, var(--voice-accent) 10%, white)' }}
          >
            <div className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: 'var(--voice-accent)' }} />
            <div>
              <div className="flex items-center justify-between gap-4">
                {safeLogo ? (
                  // Public tenant assets are validated as HTTPS and intentionally avoid Next image host allowlists.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={safeLogo} alt={messages.logoAlt} className="max-h-12 max-w-40 object-contain" />
                ) : (
                  <span className="grid size-11 place-items-center rounded-2xl bg-white shadow-sm" aria-hidden="true">
                    <ShieldCheck className="size-5" style={{ color: 'var(--voice-accent)' }} />
                  </span>
                )}
                <span className="rounded-full border border-black/10 bg-white/70 px-3 py-1 text-xs font-medium text-slate-600">
                  {messages.version} {experience.version}
                </span>
              </div>
              <p className="mt-8 text-xs font-semibold uppercase tracking-[0.22em] text-slate-600">{messages.eyebrow}</p>
              <h1 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
                {experience.content.title}
              </h1>
              {experience.content.description ? (
                <p className="mt-4 max-w-xl text-pretty text-base leading-7 text-slate-600">{experience.content.description}</p>
              ) : null}
            </div>
            {isSplit ? (
              <div className="mt-10 hidden items-center gap-2 text-sm text-slate-600 lg:flex">
                <LockKeyhole className="size-4" aria-hidden="true" />
                {messages.noticeTitle}
              </div>
            ) : null}
          </header>

          <div className="px-6 py-8 sm:px-10 sm:py-10">
            <div className="space-y-5" aria-label={experience.content.title}>
              {experience.fields.length ? (
                experience.fields.map((field) => (
                  <div key={field.key}>
                    <label htmlFor={`public-field-${field.key}`} className="text-sm font-semibold text-slate-800">
                      {field.label}
                      {field.required ? <span className="ml-1 text-rose-600">* <span className="sr-only">{messages.required}</span></span> : null}
                    </label>
                    {field.field_type !== 'checkbox' && field.description ? (
                      <p className="mt-1 text-sm leading-5 text-slate-500">{field.description}</p>
                    ) : null}
                    <FieldControl field={field} placeholder={messages.selectPlaceholder} />
                  </div>
                ))
              ) : (
                <p className="rounded-xl border border-dashed border-slate-300 px-4 py-5 text-sm text-slate-500">{messages.emptyFields}</p>
              )}

              {experience.consent.label ? (
                <div className="flex gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded border border-slate-300 bg-white" aria-hidden="true">
                    <Check className="size-3 text-slate-300" />
                  </span>
                  <p className="text-sm leading-6 text-slate-600">
                    {experience.consent.label}
                    {experience.consent.required ? <span className="ml-1 text-rose-600">*</span> : null}
                    {safePrivacy ? (
                      <a className="ml-1 font-semibold underline underline-offset-4" href={safePrivacy} target="_blank" rel="noreferrer">
                        {messages.privacy}
                      </a>
                    ) : null}
                  </p>
                </div>
              ) : null}

              <button
                type="button"
                disabled
                className="min-h-12 w-full rounded-xl bg-slate-200 px-5 text-sm font-semibold text-slate-700 disabled:cursor-not-allowed"
              >
                {experience.content.submit_label}
              </button>
            </div>

            <aside className="mt-6 flex gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
              <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold">{messages.noticeTitle}</p>
                <p className="mt-1 text-sm leading-5 text-amber-900/80">{messages.noticeDescription}</p>
              </div>
            </aside>
          </div>
        </section>
      </Shell>
    </div>
  );
}
