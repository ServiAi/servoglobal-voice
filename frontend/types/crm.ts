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

