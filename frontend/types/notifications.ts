export type NotificationOverviewResponse = {
  capabilities: { total: number; enabled: number };
  rules: { total: number; enabled: number };
  recipients: { total: number; active: number };
  deliveries: {
    pending: number;
    processing: number;
    sent: number;
    delivered: number;
    read: number;
    failed: number;
    dead_letter: number;
    manual_review: number;
    cancelled: number;
  };
};

export type NotificationCatalogResponse = {
  event_types: string[];
  capability_keys: string[];
  channels: string[];
  action_types: string[];
  recipient_strategies: string[];
  schedule_modes: string[];
  condition_operators: string[];
  variable_sources: string[];
  variable_formats: string[];
};

export type NotificationCapabilityItem = {
  capability_key: string;
  enabled: boolean;
  updated_at: string | null;
};

export type NotificationCapabilityUpdateRequest = {
  enabled: boolean;
};

export type NotificationConditionOperator =
  | 'equals'
  | 'not_equals'
  | 'in'
  | 'not_in'
  | 'exists'
  | 'not_exists'
  | 'not_empty'
  | 'greater_than'
  | 'greater_than_or_equal'
  | 'less_than'
  | 'less_than_or_equal';

export type NotificationCondition = {
  field: string;
  operator: NotificationConditionOperator;
  value?: unknown;
};

export type NotificationVariableSpec = {
  source: 'event_field' | 'literal';
  path?: string | null;
  value?: string | number | boolean | null;
  format?: 'string' | 'date_iso' | 'date_dmy' | 'time_24h' | 'datetime_iso' | 'datetime_dmy_24h';
  timezone?: string | null;
  timezone_path?: string | null;
  required?: boolean;
  default?: string | number | boolean | null;
};

export type NotificationRuleItem = {
  id: string;
  name: string;
  capability_key: string;
  event_type: string;
  channel: string;
  action_type: string;
  template_key: string | null;
  recipient_strategy: string;
  recipient_group_key: string | null;
  conditions_json: NotificationCondition[];
  variable_mapping_json: Record<string, NotificationVariableSpec>;
  schedule_mode: string;
  schedule_offset_minutes: number;
  priority: number;
  enabled: boolean;
  configuration_error: string | null;
  created_at: string;
  updated_at: string;
};

export type NotificationRuleCreateRequest = {
  name: string;
  capability_key: string;
  event_type: string;
  template_key: string;
  recipient_strategy: string;
  recipient_group_key?: string | null;
  conditions_json?: NotificationCondition[];
  variable_mapping_json?: Record<string, NotificationVariableSpec>;
  schedule_mode?: string;
  schedule_offset_minutes?: number;
  priority?: number;
  enabled?: boolean;
};

export type NotificationRuleUpdateRequest = Partial<NotificationRuleCreateRequest>;

export type NotificationRecipientItem = {
  id: string;
  group_key: string;
  name: string;
  channel: string;
  destination_masked: string;
  status: 'active' | 'inactive';
  created_at: string;
  updated_at: string;
};

export type NotificationRecipientCreateRequest = {
  group_key: string;
  name: string;
  channel?: string;
  destination: string;
  status?: 'active' | 'inactive';
};

export type NotificationRecipientUpdateRequest = Partial<Omit<NotificationRecipientCreateRequest, 'channel'>>;

export type NotificationDeliveryStatus =
  | 'pending'
  | 'processing'
  | 'sent'
  | 'delivered'
  | 'read'
  | 'failed'
  | 'skipped'
  | 'cancelled'
  | 'dead_letter'
  | 'manual_review';

export type NotificationDeliveryItem = {
  id: string;
  rule_id: string;
  rule_name: string | null;
  event_type: string | null;
  channel: string;
  recipient_masked: string;
  template_key: string | null;
  status: NotificationDeliveryStatus;
  scheduled_for: string;
  attempts: number;
  provider_message_id: string | null;
  error_code: string | null;
  sent_at: string | null;
  delivered_at: string | null;
  read_at: string | null;
  failed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type NotificationDeliveryListResponse = {
  items: NotificationDeliveryItem[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

export type NotificationDeliveryFilters = {
  page?: number;
  page_size?: number;
  status_filter?: string;
  event_type?: string;
  rule_id?: string;
  date_from?: string;
  date_to?: string;
  scheduled_from?: string;
  scheduled_to?: string;
};
