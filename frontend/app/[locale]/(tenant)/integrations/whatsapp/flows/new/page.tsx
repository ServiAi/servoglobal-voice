import { redirect } from 'next/navigation';
import { WhatsAppFlowCreate } from '@/components/crm/integrations/whatsapp-flows/WhatsAppFlowCreate';
import { fetchVoiceAgents } from '@/lib/api/crm';
import { fetchMeProfile } from '@/lib/api/me';
import { fetchVoiceContextSchemas } from '@/lib/api/voice-experiences';
import { getIntegrationAccess } from '@/lib/integrations/server';
import type { WhatsAppFlowContextSchemaOption } from '@/types/whatsapp-flows';

export const dynamic = 'force-dynamic';

export default async function NewWhatsAppFlowPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  const token = await getIntegrationAccess(locale, 'whatsapp');
  const [profileResult, agentsResult] = await Promise.all([fetchMeProfile(token), fetchVoiceAgents(token)]);
  if (!profileResult.ok || !['platform_admin', 'tenant_admin'].includes(profileResult.profile.role)) {
    redirect(`/${locale}/integrations/whatsapp/flows`);
  }
  const agents = agentsResult.ok ? agentsResult.data : [];
  const schemaResults = await Promise.all(agents.map(async (agent) => ({
    agent,
    result: await fetchVoiceContextSchemas(token, agent.id),
  })));
  const schemas: WhatsAppFlowContextSchemaOption[] = schemaResults.flatMap(({ agent, result }) => result.ok ? result.data.map((schema) => ({
    id: schema.id,
    name: schema.name,
    schema_key: schema.schema_key,
    version: schema.version,
    status: schema.status,
    agent_name: agent.display_name,
  })) : []);
  return <WhatsAppFlowCreate locale={locale} schemas={schemas} />;
}
