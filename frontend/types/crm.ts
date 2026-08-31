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

export type CrmVoiceCapacityEvent = {
  event_type: 'capacity_reached' | 'reconciled' | 'forced_release';
  occurred_at: string;
  active_calls?: number | null;
  max_concurrent_calls?: number | null;
  resulting_status?: string | null;
};

export type CrmVoiceCapacityMetrics = {
  configured: boolean;
  route_status?: string | null;
  provision_status?: string | null;
  active_calls: number;
  max_concurrent_calls: number;
  available_slots: number;
  utilization_percent: number;
  capacity_rejections: number;
  reconciled_calls: number;
  forced_releases: number;
  recent_events: CrmVoiceCapacityEvent[];
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
  voice_capacity: CrmVoiceCapacityMetrics;
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

export type IntegrationProvider = 'resend' | 'voice' | 'whatsapp' | 'calcom' | 'google_calendar';

export type IntegrationAvailabilityResponse = {
  provider: IntegrationProvider;
  enabled: boolean;
};

export type ResendTestEmailRequest = {
  to_email: string;
};

export type WhatsAppConfigRequest = {
  phone_number_id: string;
  business_account_id?: string | null;
  display_phone_number?: string | null;
  default_language?: string;
  status?: string;
  access_token?: string | null;
  webhook_verify_token?: string | null;
};

export type WhatsAppConfigResponse = {
  provider: 'whatsapp_cloud';
  status: 'active' | 'inactive' | 'error' | string;
  phone_number_id?: string | null;
  business_account_id?: string | null;
  display_phone_number?: string | null;
  default_language: string;
  has_secret: boolean;
  has_webhook_secret: boolean;
  voice_calling_enabled: boolean;
  last_health_check_at?: string | null;
  last_error_message?: string | null;
};

export type WhatsAppTestResponse = {
  status: string;
  message?: string | null;
  sends_message: boolean;
  error_message?: string | null;
};

export type WhatsAppTemplateResponse = {
  id: string;
  template_key: string;
  provider_template_name: string;
  name: string;
  category: string;
  language: string;
  body: string;
  variables: Record<string, unknown>;
  status: string;
};

export type WhatsAppTemplateSyncResponse = {
  status: string;
  fetched_count: number;
  approved_count: number;
  synced_count: number;
  ignored_count: number;
  error_message?: string | null;
};

export type WhatsAppTemplateButtonItem = {
  type: 'QUICK_REPLY' | 'URL' | 'PHONE_NUMBER' | 'VOICE_CALL' | 'FLOW';
  text: string;
  url?: string | null;
  phone_number?: string | null;
  flow_id?: string | null;
  flow_action?: string | null;
  navigate_screen?: string | null;
};

export type WhatsAppTemplateCreateRequest = {
  template_key: string;
  name: string;
  category: string;
  language?: string;
  header_text?: string | null;
  body: string;
  footer_text?: string | null;
  buttons?: WhatsAppTemplateButtonItem[];
};

export type WhatsAppTemplateUpdateRequest = {
  name?: string;
  header_text?: string | null;
  body?: string;
  footer_text?: string | null;
  buttons?: WhatsAppTemplateButtonItem[];
};

export type WhatsAppTemplateDetailResponse = WhatsAppTemplateResponse & {
  meta_status?: string | null;
  provider_template_id?: string | null;
  source: string;
  parameter_format: string;
  header_text?: string | null;
  footer_text?: string | null;
  buttons: WhatsAppTemplateButtonItem[];
  rejection_reason?: string | null;
  last_synced_at?: string | null;
};

export type WhatsAppTemplatePreviewResponse = {
  header_text?: string | null;
  body: string;
  footer_text?: string | null;
  buttons: WhatsAppTemplateButtonItem[];
  variables: Record<string, string>;
};

export type WhatsAppTemplateSubmitResponse = {
  status: string;
  meta_status?: string | null;
  provider_template_id?: string | null;
  error_message?: string | null;
};

export type WhatsAppTestMessageRequest = {
  to_phone: string;
  template_key?: string | null;
  provider_template_name?: string | null;
  language?: string | null;
  variables?: Record<string, string>;
};

export type WhatsAppTestMessageResponse = {
  status: string;
  whatsapp_message_id?: string | null;
  provider_message_id?: string | null;
  template_key?: string | null;
  to_phone_masked?: string | null;
  message?: string | null;
  error_message?: string | null;
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

export type WhatsAppActionRequest = {
  template_key: string;
  message?: string | null;
  variables?: Record<string, unknown>;
  preview_only?: boolean;
};

export type WhatsAppActionResponse = {
  status: 'preview' | 'sent' | 'failed' | string;
  whatsapp_message_id?: string | null;
  provider_message_id?: string | null;
  preview?: {
    to_phone: string;
    template_key: string;
    provider_template_name: string;
    message: string;
    variables: Record<string, unknown>;
  } | null;
  error_message?: string | null;
};

export type WhatsAppMessageResponse = {
  id: string;
  lead_id?: string | null;
  contact_id?: string | null;
  template_key?: string | null;
  provider_message_id?: string | null;
  direction: 'inbound' | 'outbound' | string;
  to_phone?: string | null;
  from_phone?: string | null;
  message_preview?: string | null;
  status: string;
  error_message?: string | null;
  sent_at?: string | null;
  delivered_at?: string | null;
  read_at?: string | null;
  failed_at?: string | null;
  created_at: string;
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

export type VoiceProviderConfigRequest = {
  provider?: string;
  display_name?: string | null;
  api_key?: string | null;
  webhook_secret?: string | null;
  base_url?: string | null;
  default_voice_agent_id?: string | null;
  default_from_number?: string | null;
  default_language?: string;
  default_timezone?: string;
  status?: string;
  sip_route?: VoiceSipRouteRequest | null;
};

export type VoiceSipRouteRequest = {
  status: 'active' | 'inactive';
  pbx_host: string;
  pbx_port: number;
  sip_password?: string | null;
  caller_id: string;
  default_country: VoiceOutboundCountry;
  allowed_countries: VoiceOutboundCountry[];
  max_concurrent_calls: number;
};

export type VoiceOutboundCountry = 'AR' | 'CL' | 'CO' | 'EC' | 'MX' | 'PA' | 'PE' | 'US';

export type VoiceSipRouteResponse = Omit<VoiceSipRouteRequest, 'sip_password'> & {
  id: string;
  sip_username: string;
  has_sip_password: boolean;
  provision_status: 'pending' | 'active' | 'failed' | 'disabled';
  desired_revision: number;
  applied_revision: number;
  provision_error_code?: string | null;
  provisioned_at?: string | null;
  last_provision_attempt_at?: string | null;
};

export type VoiceProviderConfigResponse = {
  id: string;
  provider: string;
  status: string;
  display_name?: string | null;
  base_url?: string | null;
  default_voice_agent_id?: string | null;
  default_from_number?: string | null;
  default_language: string;
  default_timezone: string;
  has_secret: boolean;
  has_webhook_secret: boolean;
  last_health_check_at?: string | null;
  last_error_message?: string | null;
  sip_route?: VoiceSipRouteResponse | null;
};

export type VoiceAgentConfigRequest = {
  provider_config_id?: string | null;
  provider?: string;
  provider_agent_id: string;
  display_name: string;
  description?: string | null;
  purpose?: string;
  default_language?: string;
  default_timezone?: string;
  default_voice?: string | null;
  default_system_prompt?: string | null;
  default_tools_json?: Record<string, unknown>;
  status?: string;
};

export type VoiceAgentConfigResponse = {
  id: string;
  provider: string;
  provider_agent_id: string;
  display_name: string;
  description?: string | null;
  purpose: string;
  default_language: string;
  default_timezone: string;
  default_voice?: string | null;
  status: string;
};

export type VoiceCallActionRequest = {
  agent_config_id?: string | null;
  provider_agent_id?: string | null;
  to_phone?: string | null;
  context?: Record<string, unknown>;
};

export type VoiceCallActionResponse = {
  status: string;
  voice_call_id?: string | null;
  provider_call_id?: string | null;
  provider_session_id?: string | null;
  summary?: string | null;
};

export type VoiceCallResponse = {
  id: string;
  provider: string;
  provider_call_id?: string | null;
  provider_session_id?: string | null;
  provider_agent_id?: string | null;
  direction: string;
  status: string;
  started_at?: string | null;
  answered_at?: string | null;
  ended_at?: string | null;
  duration_seconds?: number | null;
  summary?: string | null;
  created_at: string;
};
