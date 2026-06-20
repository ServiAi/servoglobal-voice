import { redirect } from 'next/navigation';
import { fetchMeProfile } from '@/lib/api/me';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { CrmHeader } from '@/components/crm/CrmHeader';

type Props = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function CrmLayout({ children, params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm`);
  }

  const result = await fetchMeProfile(accessToken);

  if (!result.ok) {
    if (result.status === 401) {
      redirect(`/api/auth/login?returnTo=/${locale}/crm`);
    }
    redirect(`/${locale}/dashboard/no-access`);
  }

  const { profile } = result;

  return (
    <div className="min-h-screen bg-background text-foreground transition-colors duration-300">
      {/* Shared Navigation Header */}
      <CrmHeader
        locale={locale}
        tenantName={profile.tenant_name}
        userName={profile.name ?? profile.email}
      />

      {/* Main Content Area */}
      <main className="mx-auto max-w-[1400px] px-6 py-8">
        {children}
      </main>
    </div>
  );
}
