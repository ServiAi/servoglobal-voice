import { redirect } from 'next/navigation';

import { fetchMeProfile } from '@/lib/api/me';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function PrivateDashboardBase({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/dashboard`);
  }

  const result = await fetchMeProfile(accessToken);

  if (!result.ok && result.status === 401) {
    redirect(`/api/auth/login?returnTo=/${locale}/dashboard`);
  }

  if (!result.ok) {
    redirect(`/${locale}/dashboard/no-access`);
  }

  const { profile } = result;

  return (
    <main className="min-h-screen bg-zinc-950 px-6 py-10 text-zinc-100">
      <section className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        <header className="flex flex-col gap-4 border-b border-white/10 pb-6 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium uppercase text-cyan-300">
              ServiGlobal IA
            </p>
            <h1 className="mt-2 text-3xl font-semibold tracking-normal">
              Acceso privado
            </h1>
          </div>
          <form action="/api/auth/logout" method="get">
            <button
              type="submit"
              className="inline-flex h-10 items-center justify-center rounded-md border border-white/15 px-4 text-sm font-medium text-zinc-100 transition hover:border-cyan-300 hover:text-cyan-200"
            >
              Cerrar sesion
            </button>
          </form>
        </header>

        <section className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-5">
            <p className="text-sm text-zinc-400">Usuario</p>
            <p className="mt-2 text-lg font-medium">{profile.name ?? profile.email}</p>
            <p className="mt-1 text-sm text-zinc-400">{profile.email}</p>
          </div>
          <div className="rounded-md border border-white/10 bg-white/[0.03] p-5">
            <p className="text-sm text-zinc-400">Organizacion</p>
            <p className="mt-2 text-lg font-medium">{profile.tenant_name}</p>
            <p className="mt-1 text-sm text-zinc-400">{profile.role}</p>
          </div>
        </section>
      </section>
    </main>
  );
}
