export type PipelineStageSchema = {
  id: string;
  key: string;
  name: string;
  position: number;
  is_default: boolean;
  is_terminal: boolean;
};

export type ContactBriefSchema = {
  id: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  company?: string | null;
};

export type LeadListItem = {
  lead_id: string;
  contact_name: string;
  contact_phone?: string | null;
  contact_email?: string | null;
  company?: string | null;
  stage_key: string;
  stage_name: string;
  status: string;
  lead_score?: number | null;
  interest?: string | null;
  use_case?: string | null;
  source?: string | null;
  campaign?: string | null;
  short_summary?: string | null;
  last_activity_at?: string | null;
  last_call_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type LeadsListResponse = {
  items: LeadListItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  filters_applied: Record<string, any>;
};

export type ActivitySchema = {
  id: string;
  activity_type: string;
  title: string;
  description?: string | null;
  outcome?: string | null;
  occurred_at: string;
  call_id?: string | null;
  provider_event?: string | null;
  recording_url?: string | null;
  summary?: string | null;
  short_summary?: string | null;
  normalized_status?: string | null;
  duration_seconds?: number | null;
  billed_minutes?: number | null;
};

export type TaskResponse = {
  id: string;
  tenant_id: string;
  lead_id?: string | null;
  contact_id?: string | null;
  assigned_to_user_id?: string | null;
  title: string;
  description?: string | null;
  due_at?: string | null;
  status: string;
  priority: string;
  created_at: string;
  updated_at: string;
};

export type TaskCreateRequest = {
  lead_id?: string | null;
  contact_id?: string | null;
  title: string;
  description?: string | null;
  due_at?: string | null;
  priority?: string;
  assigned_to_user_id?: string | null;
};

export type TaskUpdateRequest = {
  title?: string;
  description?: string | null;
  due_at?: string | null;
  status?: string;
  priority?: string;
  assigned_to_user_id?: string | null;
};

export type LeadUpdateRequest = {
  interest?: string | null;
  industry?: string | null;
  use_case?: string | null;
  volume?: string | null;
  pain_point?: string | null;
  budget_range?: string | null;
  intent_level?: string | null;
  next_action?: string | null;
  lead_score?: number | null;
  status?: string | null;
  source?: string | null;
  campaign?: string | null;
};

export type StageUpdateRequest = {
  stage_key: string;
  reason?: string | null;
};

export type NoteCreateRequest = {
  note: string;
};

export type LeadDetailResponse = {
  id: string;
  status: string;
  lead_score?: number | null;
  interest?: string | null;
  industry?: string | null;
  use_case?: string | null;
  volume?: string | null;
  pain_point?: string | null;
  budget_range?: string | null;
  intent_level?: string | null;
  next_action?: string | null;
  short_summary?: string | null;
  summary?: string | null;
  source?: string | null;
  campaign?: string | null;
  created_at: string;
  updated_at: string;
  contact: ContactBriefSchema;
  stage: PipelineStageSchema;
  activities: ActivitySchema[];
  tasks: TaskResponse[];
};

export type PipelineBoardLeadItem = {
  id: string;
  contact_name: string;
  phone?: string | null;
  company?: string | null;
  short_summary?: string | null;
  last_activity_at?: string | null;
  status: string;
};

export type PipelineStageLeads = {
  id: string;
  key: string;
  name: string;
  position: number;
  count: number;
  leads: PipelineBoardLeadItem[];
};

export type PipelineBoardResponse = {
  stages: PipelineStageLeads[];
};

export type LeadsByStageMetric = {
  stage_key: string;
  stage_name: string;
  count: number;
};

export type LeadsBySourceMetric = {
  source: string;
  count: number;
};

export type LeadsByCampaignMetric = {
  campaign: string;
  count: number;
};

export type CrmMetricsResponse = {
  total_contacts: number;
  total_leads: number;
  open_leads: number;
  won_leads: number;
  lost_leads: number;
  unqualified_leads: number;
  leads_by_stage: LeadsByStageMetric[];
  leads_by_source: LeadsBySourceMetric[];
  leads_by_campaign: LeadsByCampaignMetric[];
  leads_created_today: number;
  leads_created_this_week: number;
  leads_created_this_month: number;
  scheduled_leads: number;
  voicemail_leads: number;
  follow_up_leads: number;
  pending_tasks: number;
  overdue_tasks: number;
  conversion_rate: number;
  contact_completion_rate: number;
};

export type DashboardPeriod = {
  from: string;
  to: string;
  range: string;
};

export type CrmDashboardKpis = {
  total_leads: number;
  new_leads: number;
  contacted_leads: number;
  connected_leads: number;
  qualified_leads: number;
  scheduled_leads: number;
  voicemail_leads: number;
  follow_up_leads: number;
  not_interested_leads: number;
  won_leads: number;
  lost_leads: number;
  open_leads: number;
  pending_tasks: number;
  overdue_tasks: number;
  leads_with_next_action: number;
};

export type CrmDashboardConversion = {
  contact_rate: number;
  connection_rate: number;
  qualification_rate: number;
  schedule_rate: number;
  win_rate: number;
};

export type CrmDashboardFunnelItem = {
  stage: string;
  label: string;
  count: number;
};

export type CrmDashboardSourceItem = {
  source: string;
  total_leads: number;
  qualified_leads: number;
  scheduled_leads: number;
  won_leads: number;
  conversion_rate: number;
};

export type CrmDashboardCampaignItem = {
  campaign: string;
  total_leads: number;
  qualified_leads: number;
  scheduled_leads: number;
  won_leads: number;
  conversion_rate: number;
};

export type CrmDashboardCallMetrics = {
  total_calls: number;
  answered_calls: number;
  unanswered_calls: number;
  voicemail_calls: number;
  failed_calls: number;
  average_duration_seconds: number;
  total_billed_minutes: number;
};

export type CrmPendingActionItem = {
  lead_id: string;
  contact_name: string;
  stage: string;
  next_action?: string | null;
  source?: string | null;
  campaign?: string | null;
  updated_at: string;
};

export type CrmDashboardResponse = {
  period: DashboardPeriod;
  kpis: CrmDashboardKpis;
  conversion: CrmDashboardConversion;
  funnel: CrmDashboardFunnelItem[];
  sources: CrmDashboardSourceItem[];
  campaigns: CrmDashboardCampaignItem[];
  calls: CrmDashboardCallMetrics;
  pending_actions: CrmPendingActionItem[];
};

export type ResendIntegrationConfigRequest = {
  sender_name?: string | null;
  sender_email: string;
  reply_to?: string | null;
  default_domain?: string | null;
  resend_api_key?: string | null;
};

export type ResendIntegrationConfigResponse = {
  provider: 'resend';
  status: 'active' | 'inactive' | 'error' | string;
  sender_name?: string | null;
  sender_email?: string | null;
  reply_to?: string | null;
  default_domain?: string | null;
  has_secret: boolean;
  last_health_check_at?: string | null;
  last_error_message?: string | null;
};

export type ResendTestEmailRequest = {
  to_email: string;
};

export type BookingConfigRequest = {
  cal_api_key?: string | null;
  status?: string;
  calendar_mode?: 'cal_managed' | 'crm_google_insert';
  cal_api_version?: string;
  organization_slug?: string | null;
  default_event_type_id?: number | null;
  default_event_type_slug?: string | null;
  default_username?: string | null;
  default_team_slug?: string | null;
  default_timezone?: string;
  default_language?: string;
  default_location_type?: string | null;
  default_length_minutes?: number;
};

export type BookingConfigResponse = {
  provider: 'calcom';
  status: string;
  calendar_mode: 'cal_managed' | 'crm_google_insert' | string;
  has_secret: boolean;
  default_event_type_id?: number | null;
  default_event_type_slug?: string | null;
  default_username?: string | null;
  default_team_slug?: string | null;
  organization_slug?: string | null;
  default_timezone: string;
  default_language: string;
  default_location_type?: string | null;
  default_length_minutes: number;
  last_health_check_at?: string | null;
  last_error_message?: string | null;
};

export type GoogleCalendarConnectionResponse = {
  id: string;
  status: string;
  google_account_email?: string | null;
  calendar_id: string;
  calendar_summary?: string | null;
  scopes: string[];
  last_sync_at?: string | null;
  last_error_message?: string | null;
  has_tokens: boolean;
};

export type GoogleCalendarConnectUrlResponse = {
  url: string;
};

export type BookingCreateRequest = {
  start: string;
  timezone?: string;
  event_type_id?: number | null;
  event_type_slug?: string | null;
  username?: string | null;
  team_slug?: string | null;
  organization_slug?: string | null;
  attendee_name: string;
  attendee_email: string;
  attendee_phone?: string | null;
  booking_fields_responses?: Record<string, unknown>;
  notes?: string | null;
};

export type BookingResponse = {
  id: string;
  provider: string;
  provider_booking_id?: string | null;
  provider_booking_uid?: string | null;
  status: string;
  start_at: string;
  end_at?: string | null;
  timezone: string;
  duration_minutes?: number | null;
  meeting_url?: string | null;
  attendee_name: string;
  attendee_email: string;
  attendee_phone?: string | null;
  calendar_mode: string;
  created_at: string;
};

export type EmailActionRequest = {
  template_key: string;
  subject?: string | null;
  message?: string | null;
  content_format?: 'mdx' | 'markdown' | string;
  content?: string | null;
  asset_ids?: string[];
  form_token_ids?: string[];
  preview_only?: boolean;
};

export type EmailActionResponse = {
  status: 'preview' | 'sent' | 'failed' | string;
  email_send_id?: string | null;
  provider_email_id?: string | null;
  preview?: {
    to_email: string;
    subject: string;
    html: string;
    text: string;
  } | null;
};

export type EmailTemplateItem = {
  id: string;
  template_key: string;
  name: string;
  subject: string;
  category: string;
  status: string;
  is_marketing: boolean;
};

export type EmailAssetItem = {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  status: string;
};

export type CallSummaryResponse = {
  status: 'available' | 'not_found' | string;
  summary?: string | null;
  short_summary?: string | null;
  call_date?: string | null;
  duration_seconds?: number | null;
  source?: string | null;
};

export type CallSummaryAssetRequest = {
  format: 'md' | 'txt';
};

export type CallSummaryAssetResponse = {
  asset_id: string;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
};

export type CallSummaryInsertedRequest = {
  variant: 'full' | 'short';
};

export type FormFieldItem = {
  id: string;
  key: string;
  label: string;
  field_type: 'text' | 'email' | 'phone' | 'textarea' | 'select' | 'checkbox' | string;
  required: boolean;
  options: string[];
  position: number;
};

export type TenantFormItem = {
  id: string;
  name: string;
  description?: string | null;
  status: string;
  fields: FormFieldItem[];
};

export type TenantFormCreateRequest = {
  name: string;
  description?: string | null;
  status?: string;
  fields?: Array<{
    key: string;
    label: string;
    field_type: string;
    required?: boolean;
    options?: string[];
    position?: number;
  }>;
};

export type FormTokenResponse = {
  id: string;
  form_link: string;
  expires_at: string;
};

export type PublicFormResponse = {
  form: TenantFormItem;
  lead_preview: {
    contact_name?: string | null;
  };
};

