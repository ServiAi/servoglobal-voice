import { getTranslations } from 'next-intl/server';
import Link from 'next/link';

export default async function PublicVoiceExperienceNotFound() {
  const t = await getTranslations('publicVoiceExperience.notFound');

  return (
    <main className="grid min-h-[70vh] place-items-center bg-slate-50 px-6 py-16">
      <section className="max-w-lg rounded-[2rem] border border-slate-200 bg-white p-8 text-center shadow-sm sm:p-12">
        <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">404</p>
        <h1 className="mt-4 text-3xl font-semibold tracking-tight text-slate-950">{t('title')}</h1>
        <p className="mt-3 leading-7 text-slate-600">{t('description')}</p>
        <Link href="/" className="mt-7 inline-flex min-h-11 items-center rounded-xl bg-slate-950 px-5 text-sm font-semibold text-white">
          {t('back')}
        </Link>
      </section>
    </main>
  );
}
