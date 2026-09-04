import { redirect } from 'next/navigation';
import { getTranslations } from 'next-intl/server';
import { BellRing } from 'lucide-react';
import { getAccessToken } from '@/lib/auth/server';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchWhatsAppTemplates } from '@/lib/api/crm';
import {
  fetchNotificationCapabilities,
  fetchNotificationCatalog,
  fetchNotificationDeliveries,
  fetchNotificationOverview,
  fetchNotificationRecipients,
  fetchNotificationRules,
} from '@/lib/api/notification-admin';
import { NotificationsWorkspace } from '@/components/crm/notifications/NotificationsWorkspace';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

const WRITE_ROLES = new Set(['platform_admin', 'tenant_admin']);

export default async function CrmNotificationsPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/automations/notifications`);
  }

  const t = await getTranslations({ locale, namespace: 'crm.notifications' });

  const [
    profileResult,
    overviewResult,
    catalogResult,
    capabilitiesResult,
    rulesResult,
    recipientsResult,
    deliveriesResult,
    templatesResult,
  ] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchNotificationOverview(accessToken),
    fetchNotificationCatalog(accessToken),
    fetchNotificationCapabilities(accessToken),
    fetchNotificationRules(accessToken),
    fetchNotificationRecipients(accessToken),
    fetchNotificationDeliveries(accessToken, { page: 1, page_size: 25 }),
    fetchWhatsAppTemplates(accessToken),
  ]);

  const canEdit = profileResult.ok && WRITE_ROLES.has(profileResult.profile.role);
  const loadErrorCount = [
    overviewResult.ok,
    catalogResult.ok,
    capabilitiesResult.ok,
    rulesResult.ok,
    recipientsResult.ok,
    deliveriesResult.ok,
  ].filter((ok) => !ok).length;

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex items-start gap-3 border-l-4 border-primary pl-4">
        <span className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
          <BellRing className="size-5" aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-2xl font-bold text-foreground">{t('title')}</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t('description')}</p>
        </div>
      </div>

      {loadErrorCount > 0 && (
        <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive">
          {t('loadError')}
        </div>
      )}

      <NotificationsWorkspace
        canEdit={canEdit}
        overview={overviewResult.ok ? overviewResult.data : null}
        catalog={catalogResult.ok ? catalogResult.data : null}
        initialCapabilities={capabilitiesResult.ok ? capabilitiesResult.data : []}
        initialRules={rulesResult.ok ? rulesResult.data : []}
        initialRecipients={recipientsResult.ok ? recipientsResult.data : []}
        initialDeliveries={deliveriesResult.ok ? deliveriesResult.data : null}
        whatsappTemplates={templatesResult.ok ? templatesResult.data : []}
      />
    </div>
  );
}
