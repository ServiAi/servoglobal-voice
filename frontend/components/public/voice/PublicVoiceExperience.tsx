'use client';

import { Turnstile } from '@marsidev/react-turnstile';
import type { TurnstileInstance } from '@marsidev/react-turnstile';
import { useEffect, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, ReactNode } from 'react';
import { Check, LockKeyhole, Mic, PhoneCall, ShieldCheck } from 'lucide-react';

import { submitPublicVoiceExperience } from '@/lib/api/public-voice-submissions';
import { PublicVoiceCall } from './PublicVoiceCall';
import { PublicVoiceCallback } from './PublicVoiceCallback';
import { isSafeHttpsUrl } from '@/lib/voice-experiences/url-safety';
import { resolveVoiceTheme } from '@/lib/voice-experiences/resolve-theme';
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
  loading: string;
  successTitle: string;
  verificationUnavailable: string;
  microphoneHelp: string;
  callLoading: string;
  callConnected: string;
  callDuration: string;
  voiceActivity: string;
  endCall: string;
  callEnded: string;
  callbackLoading: string;
  callbackAccepted: string;
  chooseModeTitle: string;
  chooseModeWebrtc: string;
  chooseModeWebrtcHint: string;
  chooseModeCallback: string;
  chooseModeCallbackHint: string;
  changeContactMode: string;
  errors: Record<string, string>;
}

interface Props {
  experience: PublicVoiceExperienceData;
  locale: string;
  messages: PublicVoiceMessages;
  embed?: boolean;
}

const PHONE_COUNTRIES = [
  { code: 'CO', prefix: '+57', label: 'Colombia +57' },
  { code: 'MX', prefix: '+52', label: 'México +52' },
  { code: 'AR', prefix: '+549', label: 'Argentina +54 9' },
  { code: 'PA', prefix: '+507', label: 'Panamá +507' },
  { code: 'CL', prefix: '+56', label: 'Chile +56' },
  { code: 'EC', prefix: '+593', label: 'Ecuador +593' },
  { code: 'PE', prefix: '+51', label: 'Perú +51' },
  { code: 'US', prefix: '+1', label: 'Estados Unidos +1' },
] as const;

type PhoneCountry = (typeof PHONE_COUNTRIES)[number]['code'];

function PhoneFieldControl({
  field,
  defaultCountry,
  allowedCountries,
}: {
  field: PublicVoiceContextField;
  defaultCountry: PhoneCountry;
  allowedCountries: PhoneCountry[];
}) {
  const countries = PHONE_COUNTRIES.filter((country) => allowedCountries.includes(country.code));
  const initialCountry = countries.some((country) => country.code === defaultCountry)
    ? defaultCountry
    : countries[0]?.code ?? 'CO';
  const [countryCode, setCountryCode] = useState<PhoneCountry>(initialCountry);
  const [nationalNumber, setNationalNumber] = useState('');
  const country = PHONE_COUNTRIES.find((item) => item.code === countryCode) ?? PHONE_COUNTRIES[0];
  const digits = nationalNumber.replace(/\D/g, '').replace(/^0+/, '');

  return (
    <div className="mt-2 grid gap-2 sm:grid-cols-[minmax(150px,0.8fr)_1.2fr]">
      <select
        aria-label="País"
        className="min-h-11 rounded-xl border border-slate-300 bg-white px-3 text-sm text-slate-900"
        value={countryCode}
        onChange={(event) => setCountryCode(event.target.value as PhoneCountry)}
      >
        {countries.map((item) => <option key={item.code} value={item.code}>{item.label}</option>)}
      </select>
      <input
        id={`public-field-${field.key}`}
        type="tel"
        inputMode="tel"
        autoComplete="tel-national"
        required={field.required}
        value={nationalNumber}
        onChange={(event) => setNationalNumber(event.target.value)}
        placeholder="Número nacional"
        className="min-h-11 rounded-xl border border-slate-300 bg-white px-3.5 text-sm text-slate-900 outline-none transition focus:border-[var(--voice-accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--voice-accent)_18%,transparent)]"
      />
      <input type="hidden" name={field.key} value={digits ? `${country.prefix}${digits}` : ''} />
    </div>
  );
}

function FieldControl({
  field,
  placeholder,
  defaultCountry,
  allowedCountries,
}: {
  field: PublicVoiceContextField;
  placeholder: string;
  defaultCountry: PhoneCountry;
  allowedCountries: PhoneCountry[];
}) {
  if (field.field_type === 'phone') {
    return <PhoneFieldControl field={field} defaultCountry={defaultCountry} allowedCountries={allowedCountries} />;
  }
  const common = {
    id: `public-field-${field.key}`,
    name: field.key,
    required: field.required && field.field_type !== 'checkbox',
    className:
      'mt-2 min-h-11 w-full rounded-xl border border-slate-300 bg-white px-3.5 text-sm text-slate-900 outline-none transition focus:border-[var(--voice-accent)] focus:ring-2 focus:ring-[color-mix(in_srgb,var(--voice-accent)_18%,transparent)]',
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

  return <input {...common} type={type} step={field.field_type === 'integer' ? 1 : undefined} />;
}

function Shell({
  children,
  layout,
  embed,
}: {
  children: ReactNode;
  layout: PublicVoiceExperienceData['theme']['layout'];
  embed: boolean;
}) {
  return (
    <main
      className={
        embed
          ? `px-2 py-2 sm:px-3 sm:py-3 ${layout === 'split' ? 'lg:grid lg:place-items-center' : ''}`
          : `min-h-screen px-4 py-10 sm:px-6 sm:py-16 ${layout === 'split' ? 'lg:grid lg:place-items-center' : ''}`
      }
      data-testid="public-voice-runtime"
    >
      {children}
    </main>
  );
}

export function PublicVoiceExperience({ experience, locale, messages, embed = false }: Props) {
  const testMode = process.env.NEXT_PUBLIC_VOICE_PUBLIC_TURNSTILE_TEST_MODE === '1';
  const siteKey = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY;
  const turnstileRef = useRef<TurnstileInstance>();
  const rootRef = useRef<HTMLDivElement>(null);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [widgetKey, setWidgetKey] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [contextToken, setContextToken] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [selectedCallMode, setSelectedCallMode] = useState<'webrtc' | 'callback' | null>(null);

  useEffect(() => {
    if (testMode) setTurnstileToken(`playwright-${crypto.randomUUID()}`);
  }, [testMode, widgetKey]);

  useEffect(() => {
    if (!embed || typeof window === 'undefined' || window.parent === window) return;
    const el = rootRef.current;
    if (!el) return;
    const post = () =>
      window.parent.postMessage(
        { type: 'voice-embed:resize', slug: experience.slug, height: el.scrollHeight },
        '*'
      );
    const observer = new ResizeObserver(post);
    observer.observe(el);
    post();
    return () => observer.disconnect();
  }, [embed, experience.slug]);

  const resetTurnstile = () => {
    setTurnstileToken(null);
    turnstileRef.current?.reset();
    setWidgetKey((value) => value + 1);
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!turnstileToken || isSubmitting) return;

    const form = event.currentTarget;
    const data = new FormData(form);
    const answers: Record<string, string | number | boolean | null> = {};
    for (const field of experience.fields) {
      if (field.field_type === 'checkbox') {
        answers[field.key] = data.has(field.key);
        continue;
      }
      const raw = data.get(field.key);
      if (typeof raw !== 'string' || (!field.required && raw === '')) continue;
      answers[field.key] = field.field_type === 'integer' ? Number(raw) : raw;
    }

    setIsSubmitting(true);
    setErrorCode(null);
    setFieldErrors({});
    const result = await submitPublicVoiceExperience(experience.slug, {
      version: experience.version,
      locale,
      answers,
      consent: data.has('consent'),
      turnstile_token: turnstileToken,
      hp: String(data.get('hp') || ''),
    });
    setIsSubmitting(false);
    if (result.ok) {
      setContextToken(result.data.context_token);
      setIsSuccess(true);
      return;
    }
    setErrorCode(result.error.code);
    setFieldErrors(Object.fromEntries(result.error.fields.map((item) => [item.key, item.code])));
    resetTurnstile();
  };

  const safeLogo = isSafeHttpsUrl(experience.theme.logo_url) ? experience.theme.logo_url : null;
  const safePrivacy = isSafeHttpsUrl(experience.consent.privacy_url) ? experience.consent.privacy_url : null;
  const tokens = resolveVoiceTheme(experience.theme);
  const style = {
    '--voice-accent': tokens.accent,
    backgroundColor: tokens.pageBg,
    color: tokens.fg,
  } as CSSProperties;
  const isSplit = experience.theme.layout === 'split';

  return (
    <div ref={rootRef} style={style} className={embed ? '' : 'min-h-screen'}>
      <Shell layout={experience.theme.layout} embed={embed}>
        <section
          className={`mx-auto overflow-hidden border shadow-[0_24px_80px_-36px_rgba(15,23,42,0.38)] ${
            isSplit ? 'max-w-5xl rounded-[2rem] lg:grid lg:grid-cols-[0.78fr_1.22fr]' : 'max-w-2xl rounded-[2rem]'
          }`}
          style={{ backgroundColor: tokens.cardBg, color: tokens.fg, borderColor: tokens.border }}
        >
          <header
            className={`relative overflow-hidden px-6 py-8 sm:px-10 ${isSplit ? 'lg:flex lg:min-h-[620px] lg:flex-col lg:justify-between lg:py-12' : ''}`}
            style={{ backgroundColor: tokens.headerTint }}
          >
            <div className="absolute inset-y-0 left-0 w-1.5" style={{ backgroundColor: 'var(--voice-accent)' }} />
            <div>
              <div className="flex items-center justify-between gap-4">
                {safeLogo ? (
                  // Public tenant assets are validated as HTTPS and intentionally avoid Next image host allowlists.
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={safeLogo} alt={messages.logoAlt} className="max-h-12 max-w-40 object-contain" />
                ) : (
                  <span className="grid size-11 place-items-center rounded-2xl shadow-sm" style={{ backgroundColor: tokens.cardBg }} aria-hidden="true">
                    <ShieldCheck className="size-5" style={{ color: 'var(--voice-accent)' }} />
                  </span>
                )}
                <span
                  className="rounded-full border px-3 py-1 text-xs font-medium"
                  style={{ borderColor: tokens.border, color: tokens.mutedFg }}
                >
                  {messages.version} {experience.version}
                </span>
              </div>
              <p className="mt-8 text-xs font-semibold uppercase tracking-[0.22em]" style={{ color: tokens.mutedFg }}>{messages.eyebrow}</p>
              <h1 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.035em] sm:text-4xl">
                {experience.content.title}
              </h1>
              {experience.content.description ? (
                <p className="mt-4 max-w-xl text-pretty text-base leading-7" style={{ color: tokens.mutedFg }}>{experience.content.description}</p>
              ) : null}
            </div>
            {isSplit ? (
              <div className="mt-10 hidden items-center gap-2 text-sm lg:flex" style={{ color: tokens.mutedFg }}>
                <LockKeyhole className="size-4" aria-hidden="true" />
                {messages.noticeTitle}
              </div>
            ) : null}
          </header>

          <div className="px-6 py-8 sm:px-10 sm:py-10">
            {isSuccess ? (
              <div className="grid min-h-72 place-items-center text-center" role="status">
                <div>
                  <span className="mx-auto grid size-14 place-items-center rounded-full bg-emerald-100 text-emerald-700">
                    <Check className="size-7" aria-hidden="true" />
                  </span>
                  <h2 className="mt-5 text-xl font-semibold">{messages.successTitle}</h2>
                  <p className="mt-2 text-sm leading-6" style={{ color: tokens.mutedFg }}>{experience.content.success_message}</p>
                  {contextToken && experience.capabilities.calls ? (
                    experience.call_settings.mode === 'both' && !selectedCallMode ? (
                      <div className="mt-7 grid gap-3 text-left sm:grid-cols-2" role="group" aria-label={messages.chooseModeTitle}>
                        <p className="text-sm font-semibold sm:col-span-2" style={{ color: tokens.fg }}>{messages.chooseModeTitle}</p>
                        <button
                          type="button"
                          onClick={() => setSelectedCallMode('webrtc')}
                          className="rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-[var(--voice-accent)] hover:shadow-sm"
                        >
                          <Mic className="size-5" style={{ color: 'var(--voice-accent)' }} aria-hidden="true" />
                          <p className="mt-2 text-sm font-semibold" style={{ color: tokens.fg }}>{messages.chooseModeWebrtc}</p>
                          <p className="mt-1 text-xs leading-5" style={{ color: tokens.mutedFg }}>{messages.chooseModeWebrtcHint}</p>
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedCallMode('callback')}
                          className="rounded-2xl border border-slate-200 bg-white p-4 text-left transition hover:border-[var(--voice-accent)] hover:shadow-sm"
                        >
                          <PhoneCall className="size-5" style={{ color: 'var(--voice-accent)' }} aria-hidden="true" />
                          <p className="mt-2 text-sm font-semibold" style={{ color: tokens.fg }}>{messages.chooseModeCallback}</p>
                          <p className="mt-1 text-xs leading-5" style={{ color: tokens.mutedFg }}>{messages.chooseModeCallbackHint}</p>
                        </button>
                      </div>
                    ) : (experience.call_settings.mode === 'callback' ||
                        (experience.call_settings.mode === 'both' && selectedCallMode === 'callback')) ? (
                      <>
                        <PublicVoiceCallback
                          slug={experience.slug}
                          contextToken={contextToken}
                          callLabel={experience.content.call_label}
                          messages={messages}
                        />
                        {experience.call_settings.mode === 'both' ? (
                          <button
                            type="button"
                            onClick={() => setSelectedCallMode(null)}
                            className="mt-3 text-sm font-semibold underline underline-offset-4"
                            style={{ color: tokens.mutedFg }}
                          >
                            {messages.changeContactMode}
                          </button>
                        ) : null}
                      </>
                    ) : (
                      <>
                        <PublicVoiceCall
                          slug={experience.slug}
                          contextToken={contextToken}
                          callLabel={experience.content.call_label}
                          autoStart={experience.call_settings.auto_start}
                          showMicrophoneHelp={experience.call_settings.show_microphone_help}
                          messages={messages}
                        />
                        {experience.call_settings.mode === 'both' ? (
                          <button
                            type="button"
                            onClick={() => setSelectedCallMode(null)}
                            className="mt-3 text-sm font-semibold underline underline-offset-4"
                            style={{ color: tokens.mutedFg }}
                          >
                            {messages.changeContactMode}
                          </button>
                        ) : null}
                      </>
                    )
                  ) : null}
                </div>
              </div>
            ) : (
            <form className="space-y-5" aria-label={experience.content.title} onSubmit={handleSubmit}>
              {experience.fields.length ? (
                experience.fields.map((field) => (
                  <div key={field.key}>
                    <label htmlFor={`public-field-${field.key}`} className="text-sm font-semibold" style={{ color: tokens.fg }}>
                      {field.label}
                      {field.required ? <span className="ml-1 text-rose-600">* <span className="sr-only">{messages.required}</span></span> : null}
                    </label>
                    {field.field_type !== 'checkbox' && field.description ? (
                      <p className="mt-1 text-sm leading-5" style={{ color: tokens.mutedFg }}>{field.description}</p>
                    ) : null}
                    <FieldControl
                      field={field}
                      placeholder={messages.selectPlaceholder}
                      defaultCountry={experience.call_settings.default_country}
                      allowedCountries={experience.call_settings.allowed_countries.length
                        ? experience.call_settings.allowed_countries
                        : [experience.call_settings.default_country]}
                    />
                    {fieldErrors[field.key] ? (
                      <p className="mt-1 text-sm text-rose-700" role="alert">
                        {messages.errors[fieldErrors[field.key]]}
                      </p>
                    ) : null}
                  </div>
                ))
              ) : (
                <p
                  className="rounded-xl border border-dashed px-4 py-5 text-sm"
                  style={{ borderColor: tokens.border, color: tokens.mutedFg }}
                >
                  {messages.emptyFields}
                </p>
              )}

              {experience.consent.label ? (
                <div className="flex gap-3 rounded-xl border p-4" style={{ borderColor: tokens.border, backgroundColor: tokens.headerTint }}>
                  <input id="public-consent" name="consent" type="checkbox" required={experience.consent.required} className="mt-1 size-4 shrink-0 accent-[var(--voice-accent)]" />
                  <label htmlFor="public-consent" className="text-sm leading-6" style={{ color: tokens.mutedFg }}>
                    {experience.consent.label}
                    {experience.consent.required ? <span className="ml-1 text-rose-600">*</span> : null}
                    {safePrivacy ? (
                      <a className="ml-1 font-semibold underline underline-offset-4" href={safePrivacy} target="_blank" rel="noreferrer">
                        {messages.privacy}
                      </a>
                    ) : null}
                  </label>
                </div>
              ) : null}

              <input name="hp" type="text" tabIndex={-1} autoComplete="off" className="absolute -left-[10000px] size-px" aria-hidden="true" />

              {testMode ? (
                <span data-testid="turnstile-test-mode" className="sr-only">Turnstile test mode</span>
              ) : siteKey ? (
                <Turnstile
                  key={widgetKey}
                  ref={turnstileRef}
                  siteKey={siteKey}
                  onSuccess={setTurnstileToken}
                  onExpire={() => setTurnstileToken(null)}
                  onError={() => setTurnstileToken(null)}
                  options={{ responseField: false, size: 'flexible' }}
                />
              ) : (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" role="alert">
                  {messages.verificationUnavailable}
                </p>
              )}

              {errorCode ? (
                <p className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800" role="alert">
                  {messages.errors[errorCode] || messages.errors.validation_error}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={!turnstileToken || isSubmitting}
                className="min-h-12 w-full rounded-xl px-5 text-sm font-semibold text-white transition disabled:cursor-not-allowed disabled:bg-slate-300"
                style={{ backgroundColor: turnstileToken && !isSubmitting ? 'var(--voice-accent)' : undefined }}
              >
                {isSubmitting ? messages.loading : experience.content.submit_label}
              </button>
            </form>
            )}

            {!isSuccess ? <aside className="mt-6 flex gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-emerald-950">
              <LockKeyhole className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold">{messages.noticeTitle}</p>
                <p className="mt-1 text-sm leading-5 text-emerald-900/80">{messages.noticeDescription}</p>
              </div>
            </aside> : null}
          </div>
        </section>
      </Shell>
    </div>
  );
}
