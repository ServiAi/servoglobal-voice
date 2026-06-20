import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmTasks } from '@/lib/api/crm';
import { TasksClient } from './tasks-client';
import { ArrowLeft } from 'lucide-react';
import Link from 'next/link';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function CrmTasksPage({ params, searchParams }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/tasks`);
  }

  const resolvedSearchParams = await searchParams;

  const filters = {
    status: typeof resolvedSearchParams.status === 'string' ? resolvedSearchParams.status : undefined,
    priority: typeof resolvedSearchParams.priority === 'string' ? resolvedSearchParams.priority : undefined,
  };

  const result = await fetchCrmTasks(accessToken, filters);

  if (!result.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">Error al cargar tareas</h3>
        <p className="mt-2 text-sm">{result.detail}</p>
        <Link
          href={`/${locale}/crm`}
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold hover:underline"
        >
          <ArrowLeft className="h-4 w-4" /> Volver al Dashboard
        </Link>
      </div>
    );
  }

  return (
    <TasksClient
      tasks={result.data}
      accessToken={accessToken}
      locale={locale}
    />
  );
}
