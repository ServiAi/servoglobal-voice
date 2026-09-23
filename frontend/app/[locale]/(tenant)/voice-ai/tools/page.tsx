import { redirect } from 'next/navigation';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchCustomTools } from '@/lib/api/tools-custom';
import { getAccessToken } from '@/lib/auth/server';
import { canEditCustomTools, canReadCustomTools, resolveCustomToolsGateState } from '@/lib/permissions/tools';
import { ToolsWorkspace } from '@/components/crm/tools/ToolsWorkspace';

export const dynamic = 'force-dynamic';

export default async function CustomToolsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) redirect(`/api/auth/login?returnTo=/${locale}/voice-ai/tools`);

  const [profileResult, toolsResult] = await Promise.all([
    fetchMeProfile(accessToken),
    fetchCustomTools(accessToken),
  ]);

  const gateState = resolveCustomToolsGateState({
    canRead: profileResult.ok && canReadCustomTools(profileResult.profile),
    listStatus: toolsResult.ok ? null : toolsResult.status,
  });

  return (
    <ToolsWorkspace
      canEdit={profileResult.ok && canEditCustomTools(profileResult.profile)}
      initialTools={toolsResult.ok ? toolsResult.data : []}
      gateState={gateState}
    />
  );
}
