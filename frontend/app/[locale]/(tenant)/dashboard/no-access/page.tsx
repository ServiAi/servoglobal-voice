import Link from 'next/link';

import { locales, type Locale } from '@/i18n';

type Props = {
  params: Promise<{ locale: string }>;
};

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function NoAccessPage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto flex w-full max-w-3xl flex-col gap-6">
        <header className="border-b border-white/10 pb-6">
          <p className="text-sm font-medium uppercase text-cyan-300">
            ServiGlobal IA
          </p>
          <h1 className="mt-2 text-3xl font-semibold tracking-normal">Sin acceso</h1>
        </header>
        <p className="text-base text-zinc-300">
          No hay una membresia activa asociada a esta cuenta.
        </p>
        <div className="flex flex-wrap gap-3">
          <form action="/api/auth/login" method="get">
            <input type="hidden" name="returnTo" value={`/${locale}/crm`} />
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-md bg-cyan-300 px-4 text-sm font-semibold text-zinc-950 transition hover:bg-cyan-200"
            >
              Iniciar sesion
            </button>
          </form>
          <Link
            href={`/${locale}`}
            className="inline-flex h-10 items-center justify-center rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-100 transition hover:border-cyan-300 hover:text-cyan-200"
          >
            Volver
          </Link>
        </div>
      </section>
    </main>
  );
}
