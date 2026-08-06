'use server';

import { getAccessToken } from '@/lib/auth/server';
import type { FetchResult } from '@/lib/api/crm';
import {
  createNotificationRecipient,
  createNotificationRule,
  deleteNotificationRule,
  fetchNotificationDeliveries,
  fetchNotificationDelivery,
  setNotificationRuleEnabled,
  testNotificationRule,
  updateNotificationCapability,
  updateNotificationRecipient,
  updateNotificationRule,
} from '@/lib/api/notification-admin';
import type {
  NotificationCapabilityItem,
  NotificationCapabilityUpdateRequest,
  NotificationDeliveryFilters,
  NotificationDeliveryItem,
  NotificationDeliveryListResponse,
  NotificationRecipientCreateRequest,
  NotificationRecipientItem,
  NotificationRecipientUpdateRequest,
  NotificationRuleCreateRequest,
  NotificationRuleItem,
  NotificationRuleTestRequest,
  NotificationRuleTestResponse,
  NotificationRuleUpdateRequest,
} from '@/types/notifications';

async function withAccessToken<T>(run: (accessToken: string) => Promise<FetchResult<T>>): Promise<FetchResult<T>> {
  const accessToken = await getAccessToken();
  if (!accessToken) {
    return { ok: false, status: 401, detail: 'unauthorized' };
  }
  return run(accessToken);
}

export async function updateNotificationCapabilityAction(
  capabilityKey: string,
  payload: NotificationCapabilityUpdateRequest
): Promise<FetchResult<NotificationCapabilityItem>> {
  return withAccessToken((accessToken) => updateNotificationCapability(accessToken, capabilityKey, payload));
}

export async function createNotificationRuleAction(
  payload: NotificationRuleCreateRequest
): Promise<FetchResult<NotificationRuleItem>> {
  return withAccessToken((accessToken) => createNotificationRule(accessToken, payload));
}

export async function updateNotificationRuleAction(
  ruleId: string,
  payload: NotificationRuleUpdateRequest
): Promise<FetchResult<NotificationRuleItem>> {
  return withAccessToken((accessToken) => updateNotificationRule(accessToken, ruleId, payload));
}

export async function testNotificationRuleAction(
  payload: NotificationRuleTestRequest
): Promise<FetchResult<NotificationRuleTestResponse>> {
  return withAccessToken((accessToken) => testNotificationRule(accessToken, payload));
}

export async function setNotificationRuleEnabledAction(
  ruleId: string,
  enabled: boolean
): Promise<FetchResult<NotificationRuleItem>> {
  return withAccessToken((accessToken) => setNotificationRuleEnabled(accessToken, ruleId, enabled));
}

export async function deleteNotificationRuleAction(ruleId: string): Promise<FetchResult<null>> {
  return withAccessToken((accessToken) => deleteNotificationRule(accessToken, ruleId));
}

export async function createNotificationRecipientAction(
  payload: NotificationRecipientCreateRequest
): Promise<FetchResult<NotificationRecipientItem>> {
  return withAccessToken((accessToken) => createNotificationRecipient(accessToken, payload));
}

export async function updateNotificationRecipientAction(
  recipientId: string,
  payload: NotificationRecipientUpdateRequest
): Promise<FetchResult<NotificationRecipientItem>> {
  return withAccessToken((accessToken) => updateNotificationRecipient(accessToken, recipientId, payload));
}

export async function fetchNotificationDeliveriesAction(
  filters?: NotificationDeliveryFilters
): Promise<FetchResult<NotificationDeliveryListResponse>> {
  return withAccessToken((accessToken) => fetchNotificationDeliveries(accessToken, filters));
}

export async function fetchNotificationDeliveryAction(
  deliveryId: string
): Promise<FetchResult<NotificationDeliveryItem>> {
  return withAccessToken((accessToken) => fetchNotificationDelivery(accessToken, deliveryId));
}
