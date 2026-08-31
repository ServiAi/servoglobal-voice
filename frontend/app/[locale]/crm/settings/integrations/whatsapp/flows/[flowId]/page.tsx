import { notFound } from 'next/navigation';
import { WhatsAppFlowStudio } from '@/components/crm/integrations/whatsapp-flows/WhatsAppFlowStudio';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchWhatsAppFlow } from '@/lib/api/whatsapp-flows';
import { getIntegrationAccess } from '@/lib/integrations/server';

export const dynamic = 'force-dynamic';

export default async function WhatsAppFlowEditorPage({ params }: { params: Promise<{ locale: string; flowId: string }> }) {
  const { locale, flowId } = await params;
  const token = await getIntegrationAccess(locale, 'whatsapp');
  const [flowResult, profileResult] = await Promise.all([fetchWhatsAppFlow(token, flowId), fetchMeProfile(token)]);
  if (!flowResult.ok && flowResult.status === 404) notFound();
  if (!flowResult.ok) return <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">{flowResult.detail}</p>;
  const canEdit = profileResult.ok && ['platform_admin', 'tenant_admin'].includes(profileResult.profile.role);
  return <WhatsAppFlowStudio locale={locale} initialFlow={flowResult.data} canEdit={canEdit} />;
}
