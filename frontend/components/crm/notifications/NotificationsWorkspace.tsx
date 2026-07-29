'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, Loader2 } from 'lucide-react';

import { updateNotificationCapabilityAction } from '@/app/[locale]/crm/settings/notifications/actions';
import type {
  NotificationCapabilityItem,
  NotificationCatalogResponse,
  NotificationDeliveryListResponse,
  NotificationOverviewResponse,
  NotificationRecipientItem,
  NotificationRuleItem,
} from '@/types/notifications';
import type { WhatsAppTemplateResponse } from '@/types/crm';
import { RulesPanel } from './RulesPanel';
import { RecipientsPanel } from './RecipientsPanel';
import { DeliveriesPanel } from './DeliveriesPanel';

type Props = {
  canEdit: boolean;
  overview: NotificationOverviewResponse | null;
  catalog: NotificationCatalogResponse | null;
  initialCapabilities: NotificationCapabilityItem[];
  initialRules: NotificationRuleItem[];
  initialRecipients: NotificationRecipientItem[];
  initialDeliveries: NotificationDeliveryListResponse | null;
  whatsappTemplates: WhatsAppTemplateResponse[];
};

type TabKey = 'overview' | 'rules' | 'recipients' | 'deliveries';

const TAB_KEYS: TabKey[] = ['overview', 'rules', 'recipients', 'deliveries'];

export function NotificationsWorkspace({
  canEdit,
  overview,
  catalog,
  initialCapabilities,
  initialRules,
  initialRecipients,
  initialDeliveries,
  whatsappTemplates,
}: Props) {
  const t = useTranslations('crm.notifications');
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  return (
    <div className="flex flex-col gap-6">
      <div role="tablist" aria-label={t('title')} className="flex flex-wrap gap-1 rounded-[var(--radius-control)] border border-border bg-muted/40 p-1">
        {TAB_KEYS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            id={`notifications-tab-${key}`}
            aria-selected={activeTab === key}
            aria-controls={`notifications-panel-${key}`}
            onClick={() => setActiveTab(key)}
            className={`min-h-9 flex-1 rounded-[calc(var(--radius-control)-2px)] px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:flex-none ${
              activeTab === key
                ? 'bg-card text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id="notifications-panel-overview"
        aria-labelledby="notifications-tab-overview"
        hidden={activeTab !== 'overview'}
      >
        {activeTab === 'overview' && (
          <OverviewTab canEdit={canEdit} overview={overview} initialCapabilities={initialCapabilities} />
        )}
      </div>

      <div
        role="tabpanel"
        id="notifications-panel-rules"
        aria-labelledby="notifications-tab-rules"
        hidden={activeTab !== 'rules'}
      >
        {activeTab === 'rules' && (
          <RulesPanel
            canEdit={canEdit}
            catalog={catalog}
            initialRules={initialRules}
            whatsappTemplates={whatsappTemplates}
          />
        )}
      </div>

      <div
        role="tabpanel"
        id="notifications-panel-recipients"
        aria-labelledby="notifications-tab-recipients"
        hidden={activeTab !== 'recipients'}
      >
        {activeTab === 'recipients' && (
          <RecipientsPanel canEdit={canEdit} initialRecipients={initialRecipients} />
        )}
      </div>

      <div
        role="tabpanel"
        id="notifications-panel-deliveries"
        aria-labelledby="notifications-tab-deliveries"
        hidden={activeTab !== 'deliveries'}
      >
        {activeTab === 'deliveries' && (
          <DeliveriesPanel initialDeliveries={initialDeliveries} rules={initialRules} catalog={catalog} />
        )}
      </div>
    </div>
  );
}

function OverviewTab({
  canEdit,
  overview,
  initialCapabilities,
}: {
  canEdit: boolean;
  overview: NotificationOverviewResponse | null;
  initialCapabilities: NotificationCapabilityItem[];
}) {
  const t = useTranslations('crm.notifications');
  const [capabilities, setCapabilities] = useState(initialCapabilities);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [errorKey, setErrorKey] = useState<string | null>(null);

  const needsAttention = overview
    ? overview.deliveries.failed + overview.deliveries.dead_letter + overview.deliveries.manual_review
    : 0;

  const cards = overview
    ? [
        { label: t('overview.capabilitiesActive'), value: overview.capabilities.enabled },
        { label: t('overview.rulesActive'), value: overview.rules.enabled },
        { label: t('overview.recipientsActive'), value: overview.recipients.active },
        { label: t('overview.pending'), value: overview.deliveries.pending },
        { label: t('overview.needsAttention'), value: needsAttention, alert: needsAttention > 0 },
      ]
    : [];

  const toggleCapability = async (capabilityKey: string, enabled: boolean) => {
    setSavingKey(capabilityKey);
    setErrorKey(null);
    const result = await updateNotificationCapabilityAction(capabilityKey, { enabled });
    setSavingKey(null);
    if (!result.ok) {
      setErrorKey(capabilityKey);
      return;
    }
    setCapabilities((current) =>
      current.map((item) => (item.capability_key === capabilityKey ? result.data : item))
    );
  };

  return (
    <div className="flex flex-col gap-6">
      <section aria-label={t('title')} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        {cards.map((card) => (
          <div
            key={card.label}
            className={`flex min-h-24 flex-col justify-between gap-2 rounded-xl border p-4 shadow-xs ${
              card.alert ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-card'
            }`}
          >
            <p className="text-sm font-medium text-muted-foreground">{card.label}</p>
            <p className={`text-2xl font-semibold ${card.alert ? 'text-destructive' : 'text-foreground'}`}>
              {card.value}
              {card.alert && <AlertTriangle aria-hidden="true" className="ml-2 inline size-4" />}
            </p>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="notification-capabilities-heading">
        <h2 id="notification-capabilities-heading" className="text-lg font-semibold text-foreground">
          {t('overview.capabilitiesTitle')}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {capabilities.map((capability) => {
            const isSaving = savingKey === capability.capability_key;
            const hasError = errorKey === capability.capability_key;
            return (
              <div
                key={capability.capability_key}
                className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4 shadow-xs"
              >
                <div>
                  <p className="text-sm font-medium text-foreground">
                    {t(`overview.capabilityKeys.${capability.capability_key}`)}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {isSaving
                      ? t('overview.capabilityState.saving')
                      : hasError
                      ? t('overview.capabilityState.error')
                      : capability.enabled
                      ? t('overview.capabilityState.active')
                      : t('overview.capabilityState.inactive')}
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={capability.enabled}
                  aria-label={t(`overview.capabilityKeys.${capability.capability_key}`)}
                  disabled={!canEdit || isSaving}
                  onClick={() => toggleCapability(capability.capability_key, !capability.enabled)}
                  className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${
                    capability.enabled ? 'bg-primary' : 'bg-muted'
                  }`}
                >
                  {isSaving ? (
                    <Loader2 aria-hidden="true" className="mx-auto size-4 animate-spin text-primary-foreground" />
                  ) : (
                    <span
                      className={`inline-block size-4 transform rounded-full bg-background transition-transform ${
                        capability.enabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  )}
                </button>
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
