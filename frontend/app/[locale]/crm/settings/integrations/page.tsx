import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { fetchTenantIntegrations } from '@/lib/api/crm';
import { ResendIntegrationCard } from '@/components/crm/integrations/ResendIntegrationCard';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

export default async function CrmIntegrationsPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/settings/integrations`);
  }
  const integrationsResult = await fetchTenantIntegrations(accessToken);
  const resendConfig = integrationsResult.ok
    ? integrationsResult.data.find((item) => item.provider === 'resend')
    : undefined;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Integraciones CRM</h1>
        <p className="text-sm text-muted-foreground">Configuracion transaccional por tenant</p>
      </div>
      {!integrationsResult.ok && (
        <div className="rounded-md border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-500">
          {integrationsResult.detail}
        </div>
      )}
      <ResendIntegrationCard accessToken={accessToken} initialConfig={resendConfig} />
    </div>
  );
}
