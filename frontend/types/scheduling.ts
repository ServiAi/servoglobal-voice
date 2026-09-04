export type TimeShift = {
  start: string;
  end: string;
};

export type WeeklyWorkingHours = {
  monday?: TimeShift[];
  tuesday?: TimeShift[];
  wednesday?: TimeShift[];
  thursday?: TimeShift[];
  friday?: TimeShift[];
  saturday?: TimeShift[];
  sunday?: TimeShift[];
  [key: string]: TimeShift[] | undefined;
};

export type TenantSchedulingConfig = {
  id: string;
  tenant_id: string;
  timezone: string;
  default_duration_minutes: number;
  slot_interval_minutes: number;
  buffer_before_minutes: number;
  buffer_after_minutes: number;
  minimum_notice_minutes: number;
  maximum_booking_days: number;
  routing_strategy: string;
  default_resource_id?: string | null;
  default_team_id?: string | null;
  working_hours_json?: WeeklyWorkingHours | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SchedulingResourceCalendar = {
  id: string;
  resource_id: string;
  calendar_id: string;
  is_blocking: boolean;
  is_destination: boolean;
  created_at: string;
  google_calendar_id?: string | null;
  summary?: string | null;
};

export type SchedulingResource = {
  id: string;
  tenant_id: string;
  name: string;
  resource_type: string;
  team?: string | null;
  email?: string | null;
  phone?: string | null;
  priority: number;
  is_active: boolean;
  timezone: string;
  capacity: number;
  working_hours?: WeeklyWorkingHours | null;
  total_assigned_count: number;
  last_assigned_at?: string | null;
  created_at: string;
  updated_at: string;
  calendars: SchedulingResourceCalendar[];
};

export type SchedulingTeamMember = {
  id: string;
  team_id: string;
  resource_id: string;
  priority: number;
  is_active: boolean;
  created_at: string;
  resource_name?: string | null;
  resource_email?: string | null;
};

export type SchedulingTeam = {
  id: string;
  tenant_id: string;
  name: string;
  description?: string | null;
  routing_strategy: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  members: SchedulingTeamMember[];
};

export type SchedulingAvailabilityException = {
  id: string;
  tenant_id: string;
  resource_id?: string | null;
  exception_date: string;
  exception_type: 'unavailable' | 'custom_hours';
  start_time?: string | null;
  end_time?: string | null;
  reason?: string | null;
  created_at: string;
  updated_at: string;
  resource_name?: string | null;
};

export type AgentSchedulingConfig = {
  id: string;
  tenant_id: string;
  agent_id: string;
  provider: string;
  scheduling_config_id?: string | null;
  resource_id?: string | null;
  team_id?: string | null;
  routing_strategy: string;
  duration_minutes?: number | null;
  allow_check_availability: boolean;
  allow_create_booking: boolean;
  allow_reschedule: boolean;
  allow_cancel: boolean;
  is_active: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  resource_name?: string | null;
  team_name?: string | null;
};

export type SchedulingDashboardSummary = {
  active_resources_count: number;
  teams_count: number;
  connected_calendars_count: number;
  upcoming_bookings_count: number;
  google_connected: boolean;
  availability_configured: boolean;
  agents_count: number;
  alerts: string[];
};
