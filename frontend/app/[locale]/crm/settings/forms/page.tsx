import { redirect } from 'next/navigation';
import { getAccessToken } from '@/lib/auth/server';
import { fetchTenantForms } from '@/lib/api/crm';
import { FormsSettingsClient } from '@/components/crm/forms/FormsSettingsClient';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

export default async function CrmFormsSettingsPage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm/settings/forms`);
  }
  const formsResult = await fetchTenantForms(accessToken);
  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">Formularios CRM</h1>
        <p className="text-sm text-muted-foreground">Links publicos seguros por lead</p>
      </div>
      {!formsResult.ok && (
        <div className="rounded-md border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-500">
          {formsResult.detail}
        </div>
      )}
      <FormsSettingsClient accessToken={accessToken} initialForms={formsResult.ok ? formsResult.data : []} />
    </div>
  );
}
