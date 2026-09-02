import type { IntegrationProvider, IntegrationStatus } from '@/types/crm';

export type IntegrationCategory =
  | 'communication'
  | 'voice'
  | 'scheduling'
  | 'crm'
  | 'automation'
  | 'productivity';

export type IntegrationCatalogItem = {
  provider: IntegrationProvider;
  category: IntegrationCategory;
  href: string;
  icon: 'calendar' | 'mail' | 'message' | 'phone';
};

export const integrationCategories: IntegrationCategory[] = [
  'communication',
  'voice',
  'scheduling',
  'crm',
  'automation',
  'productivity',
];

export const integrationCatalog: IntegrationCatalogItem[] = [
  { provider: 'whatsapp', category: 'communication', href: '/crm/settings/integrations/whatsapp', icon: 'message' },
  { provider: 'resend', category: 'communication', href: '/crm/settings/integrations/resend', icon: 'mail' },
  { provider: 'voice', category: 'voice', href: '/crm/settings/integrations/voice', icon: 'phone' },
  { provider: 'calcom', category: 'scheduling', href: '/crm/settings/integrations/calcom', icon: 'calendar' },
  { provider: 'google_calendar', category: 'scheduling', href: '/crm/settings/integrations/google-calendar', icon: 'calendar' },
  { provider: 'chatwoot', category: 'crm', href: '/crm/settings/integrations/chatwoot', icon: 'message' },
];

export function resolveIntegrationStatus(
  resultOk: boolean,
  config: { status?: string; last_error_message?: string | null } | undefined,
  configured: boolean,
): IntegrationStatus {
  if (!resultOk || config?.last_error_message || config?.status === 'error' || config?.status === 'failed') return 'error';
  if (!configured) return 'not_configured';
  return config?.status === 'active' || config?.status === 'connected' ? 'active' : 'configured';
}
