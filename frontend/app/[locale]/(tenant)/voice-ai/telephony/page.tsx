import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { getAccessToken } from '@/lib/auth/server';
import { locales, type Locale } from '@/i18n';
import { fetchCrmDashboard } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import { canManageVoiceCapacity } from '@/lib/permissions/voice-capacity';
import { VoiceCapacityPanel } from '@/components/voice-ai/VoiceCapacityPanel';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

function normalizeLocale(locale: string): Locale {
  return locales.includes(locale as Locale) ? (locale as Locale) : 'es';
}

export default async function VoiceAiTelephonyPage({ params }: Props) {
  const { locale: rawLocale } = await params;
  const locale = normalizeLocale(rawLocale);
  const accessToken = await getAccessToken();

  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/telephony`);
  }

  const t = await getTranslations({ locale, namespace: 'crm.voiceAi' });
  const [dashboardRes, profileRes] = await Promise.all([
    fetchCrmDashboard(accessToken),
    fetchMeProfile(accessToken),
  ]);

  if (!dashboardRes.ok) {
    return (
      <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-6 text-destructive">
        <h3 className="text-lg font-bold">{t('telephonyError')}</h3>
        <p className="mt-2 text-sm">{dashboardRes.detail}</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="border-b border-border pb-5">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">{t('telephonyTitle')}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('telephonySubtitle')}</p>
      </header>
      <VoiceCapacityPanel
        data={dashboardRes.data}
        locale={locale}
        canManageCapacity={profileRes.ok && canManageVoiceCapacity(profileRes.profile.role)}
      />
    </div>
  );
}
