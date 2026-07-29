import { requestBackendEndpoint } from './crm';
import type {
  NotificationCapabilityItem,
  NotificationCapabilityUpdateRequest,
  NotificationCatalogResponse,
  NotificationDeliveryFilters,
  NotificationDeliveryItem,
  NotificationDeliveryListResponse,
  NotificationOverviewResponse,
  NotificationRecipientCreateRequest,
  NotificationRecipientItem,
  NotificationRecipientUpdateRequest,
  NotificationRuleCreateRequest,
  NotificationRuleItem,
  NotificationRuleUpdateRequest,
} from '@/types/notifications';

function adminNotifications<T>(
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  endpoint: string,
  accessToken: string,
  queryParams?: Record<string, unknown>,
  body?: unknown
) {
  return requestBackendEndpoint<T>(
    method,
    'admin',
    endpoint ? `notifications/${endpoint}` : 'notifications',
    accessToken,
    queryParams,
    body
  );
}

export function fetchNotificationOverview(accessToken: string) {
  return adminNotifications<NotificationOverviewResponse>('GET', 'overview', accessToken);
}

export function fetchNotificationCatalog(accessToken: string) {
  return adminNotifications<NotificationCatalogResponse>('GET', 'catalog', accessToken);
}

export function fetchNotificationCapabilities(accessToken: string) {
  return adminNotifications<NotificationCapabilityItem[]>('GET', 'capabilities', accessToken);
}

export function updateNotificationCapability(
  accessToken: string,
  capabilityKey: string,
  payload: NotificationCapabilityUpdateRequest
) {
  return adminNotifications<NotificationCapabilityItem>(
    'PATCH',
    `capabilities/${capabilityKey}`,
    accessToken,
    undefined,
    payload
  );
}

export function fetchNotificationRules(accessToken: string) {
  return adminNotifications<NotificationRuleItem[]>('GET', 'rules', accessToken);
}

export function createNotificationRule(accessToken: string, payload: NotificationRuleCreateRequest) {
  return adminNotifications<NotificationRuleItem>('POST', 'rules', accessToken, undefined, payload);
}

export function updateNotificationRule(
  accessToken: string,
  ruleId: string,
  payload: NotificationRuleUpdateRequest
) {
  return adminNotifications<NotificationRuleItem>('PATCH', `rules/${ruleId}`, accessToken, undefined, payload);
}

export function setNotificationRuleEnabled(accessToken: string, ruleId: string, enabled: boolean) {
  return adminNotifications<NotificationRuleItem>(
    'PATCH',
    `rules/${ruleId}/enabled`,
    accessToken,
    undefined,
    { enabled }
  );
}

export function fetchNotificationRecipients(accessToken: string) {
  return adminNotifications<NotificationRecipientItem[]>('GET', 'recipients', accessToken);
}

export function createNotificationRecipient(accessToken: string, payload: NotificationRecipientCreateRequest) {
  return adminNotifications<NotificationRecipientItem>('POST', 'recipients', accessToken, undefined, payload);
}

export function updateNotificationRecipient(
  accessToken: string,
  recipientId: string,
  payload: NotificationRecipientUpdateRequest
) {
  return adminNotifications<NotificationRecipientItem>(
    'PATCH',
    `recipients/${recipientId}`,
    accessToken,
    undefined,
    payload
  );
}

export function fetchNotificationDeliveries(accessToken: string, filters?: NotificationDeliveryFilters) {
  return adminNotifications<NotificationDeliveryListResponse>(
    'GET',
    'deliveries',
    accessToken,
    filters as Record<string, unknown> | undefined
  );
}

export function fetchNotificationDelivery(accessToken: string, deliveryId: string) {
  return adminNotifications<NotificationDeliveryItem>('GET', `deliveries/${deliveryId}`, accessToken);
}
