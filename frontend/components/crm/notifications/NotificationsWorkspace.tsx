'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  LayoutDashboard,
  Loader2,
  Send,
  UserRoundCheck,
  UsersRound,
  Workflow,
} from 'lucide-react';

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
const TAB_ICONS = {
  overview: LayoutDashboard,
  rules: Workflow,
  recipients: UsersRound,
  deliveries: Send,
} satisfies Record<TabKey, typeof LayoutDashboard>;

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
  const tabCounts: Record<TabKey, number | null> = {
    overview: null,
    rules: initialRules.length,
    recipients: initialRecipients.length,
    deliveries: initialDeliveries?.total ?? 0,
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="border-b border-border">
        <div role="tablist" aria-label={t('title')} className="grid grid-cols-2 gap-x-4 sm:flex sm:gap-6">
          {TAB_KEYS.map((key) => {
            const Icon = TAB_ICONS[key];
            return (
              <button
                key={key}
                type="button"
                role="tab"
                id={`notifications-tab-${key}`}
                aria-selected={activeTab === key}
                aria-controls={`notifications-panel-${key}`}
                onClick={() => setActiveTab(key)}
                className={`relative flex min-h-12 items-center justify-center gap-2 border-b-2 px-1 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring sm:justify-start ${
                  activeTab === key
                    ? 'border-primary text-foreground'
                    : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                }`}
              >
                <Icon className="size-4" aria-hidden="true" />
                <span>{t(`tabs.${key}`)}</span>
                {tabCounts[key] !== null && (
                  <span className="inline-flex min-w-5 items-center justify-center rounded-full bg-muted px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-muted-foreground">
                    {tabCounts[key]}
                  </span>
                )}
              </button>
            );
          })}
        </div>
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
        { label: t('overview.capabilitiesActive'), value: overview.capabilities.enabled, icon: CheckCircle2 },
        { label: t('overview.rulesActive'), value: overview.rules.enabled, icon: Workflow },
        { label: t('overview.recipientsActive'), value: overview.recipients.active, icon: UserRoundCheck },
        { label: t('overview.pending'), value: overview.deliveries.pending, icon: Clock3 },
        { label: t('overview.needsAttention'), value: needsAttention, icon: AlertTriangle, alert: needsAttention > 0 },
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
        {cards.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.label}
              className={`flex min-h-24 items-start justify-between gap-3 rounded-lg border p-4 shadow-xs ${
                card.alert ? 'border-destructive/30 bg-destructive/5' : 'border-border bg-card'
              }`}
            >
              <div>
                <p className={`text-2xl font-semibold tabular-nums ${card.alert ? 'text-destructive' : 'text-foreground'}`}>
                  {card.value}
                </p>
                <p className="mt-2 text-sm font-medium text-muted-foreground">{card.label}</p>
              </div>
              <span className={`flex size-9 items-center justify-center rounded-md ${card.alert ? 'bg-destructive/10 text-destructive' : 'bg-muted text-muted-foreground'}`}>
                <Icon aria-hidden="true" className="size-4" />
              </span>
            </div>
          );
        })}
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
                className="flex items-center justify-between gap-3 rounded-lg border border-border bg-card p-4 shadow-xs transition-colors hover:border-primary/25"
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
                      className={`inline-block size-4 transform rounded-full bg-background shadow-sm transition-transform ${
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
