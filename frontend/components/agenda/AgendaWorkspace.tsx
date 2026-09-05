'use client';

import { useState, useTransition } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Bot,
  Calendar,
  CalendarCheck,
  CalendarDays,
  CheckCircle2,
  Clock,
  Edit2,
  ExternalLink,
  Layers,
  Loader2,
  Plus,
  RefreshCw,
  Sliders,
  Trash2,
  UserCheck,
  UserPlus,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import type {
  SchedulingAvailabilityException,
  SchedulingDashboardSummary,
  SchedulingEventType,
  SchedulingEventTypeCreateRequest,
  SchedulingProviderCapabilities,
  SchedulingResource,
  SchedulingSchedule,
  SchedulingScheduleCreateRequest,
  SchedulingTeam,
  TenantSchedulingConfig,
  WeeklyWorkingHours,
} from '@/types/scheduling';
import {
  addSchedulingTeamMemberAction,
  createEventTypeAction,
  createScheduleAction,
  createSchedulingExceptionAction,
  createSchedulingResourceAction,
  createSchedulingTeamAction,
  deleteEventTypeAction,
  deleteScheduleAction,
  deleteSchedulingExceptionAction,
  deleteSchedulingResourceAction,
  deleteSchedulingTeamAction,
  fetchEventTypesAction,
  fetchSchedulesAction,
  removeSchedulingTeamMemberAction,
  syncCalComProviderAction,
  updateEventTypeAction,
  updateScheduleAction,
  updateSchedulingConfigAction,
  upsertAgentSchedulingConfigAction,
} from '@/app/[locale]/(tenant)/agenda/actions';


type Props = {
  locale: string;
  canEdit: boolean;
  initialSummary: SchedulingDashboardSummary;
  initialConfig: TenantSchedulingConfig;
  initialResources: SchedulingResource[];
  initialTeams: SchedulingTeam[];
  initialExceptions: SchedulingAvailabilityException[];
  connectedGoogleCalendars: Array<{ id: string; google_calendar_id: string; summary?: string | null }>;
  initialProviders?: SchedulingProviderCapabilities[];
  initialSchedules?: SchedulingSchedule[];
  initialEventTypes?: SchedulingEventType[];
};

type TabKey = 'resumen' | 'event_types' | 'disponibilidad' | 'recursos' | 'equipos' | 'reglas' | 'excepciones' | 'agentes';


const WEEKDAYS = [
  { key: 'monday', label: 'Lunes' },
  { key: 'tuesday', label: 'Martes' },
  { key: 'wednesday', label: 'Miércoles' },
  { key: 'thursday', label: 'Jueves' },
  { key: 'friday', label: 'Viernes' },
  { key: 'saturday', label: 'Sábado' },
  { key: 'sunday', label: 'Domingo' },
];

export function AgendaWorkspace({
  locale,
  canEdit,
  initialSummary,
  initialConfig,
  initialResources,
  initialTeams,
  initialExceptions,
  connectedGoogleCalendars,
  initialProviders,
  initialSchedules,
  initialEventTypes,
}: Props) {
  const [activeTab, setActiveTab] = useState<TabKey>('resumen');
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // States
  const [summary] = useState(initialSummary);
  const [config, setConfig] = useState(initialConfig);
  const [resources, setResources] = useState(initialResources);
  const [teams, setTeams] = useState(initialTeams);
  const [exceptions, setExceptions] = useState(initialExceptions);
  const [providers] = useState(initialProviders ?? []);
  const [schedules, setSchedules] = useState(initialSchedules ?? []);
  const [eventTypes, setEventTypes] = useState(initialEventTypes ?? []);
  const [selectedScheduleId, setSelectedScheduleId] = useState<string>(
    initialSchedules && initialSchedules.length > 0 ? initialSchedules[0].id : ''
  );
  const [isSyncing, setIsSyncing] = useState(false);

  // Event Type Form State
  const [showEventTypeModal, setShowEventTypeModal] = useState(false);
  const [editingEventTypeId, setEditingEventTypeId] = useState<string | null>(null);
  const [eventTypeForm, setEventTypeForm] = useState<SchedulingEventTypeCreateRequest>({
    name: '',
    slug: '',
    description: '',
    duration_minutes: 30,
    slot_interval_minutes: 30,
    buffer_before_minutes: 0,
    buffer_after_minutes: 0,
    minimum_notice_minutes: 60,
    local_schedule_id: '',
    local_team_id: '',
    is_active: true,
  });

  // Schedule Form State
  const [showScheduleModal, setShowScheduleModal] = useState(false);
  const [scheduleForm, setScheduleForm] = useState<SchedulingScheduleCreateRequest>({
    name: '',
    timezone: config.timezone || 'America/Bogota',
    is_default: false,
  });

  // Resource Form State
  const [showResourceModal, setShowResourceModal] = useState(false);
  const [resForm, setResForm] = useState({
    name: '',
    email: '',
    phone: '',
    resource_type: 'user',
    priority: 1,
    capacity: 1,
    team: '',
  });

  // Team Form State
  const [showTeamModal, setShowTeamModal] = useState(false);
  const [teamForm, setTeamForm] = useState({
    name: '',
    description: '',
    routing_strategy: 'round_robin',
  });

  // Team Member Add State
  const [memberTeamId, setMemberTeamId] = useState<string | null>(null);
  const [selectedResourceId, setSelectedResourceId] = useState<string>('');

  // Exception Form State
  const [showExceptionModal, setShowExceptionModal] = useState(false);
  const [excForm, setExcForm] = useState({
    exception_date: '',
    exception_type: 'unavailable' as 'unavailable' | 'custom_hours',
    start_time: '08:00',
    end_time: '12:00',
    reason: '',
    resource_id: '',
  });


  // Agent Config Form State
  const [agentForm, setAgentForm] = useState({
    agent_id: '',
    target_type: 'team',
    target_id: '',
    duration_minutes: 30,
    allow_check_availability: true,
    allow_create_booking: true,
    allow_reschedule: true,
    allow_cancel: true,
  });

  // Availability working hours local state
  const defaultHours: WeeklyWorkingHours = config.working_hours_json || {
    monday: [{ start: '08:00', end: '12:00' }, { start: '14:00', end: '18:00' }],
    tuesday: [{ start: '08:00', end: '12:00' }, { start: '14:00', end: '18:00' }],
    wednesday: [{ start: '08:00', end: '12:00' }, { start: '14:00', end: '18:00' }],
    thursday: [{ start: '08:00', end: '12:00' }, { start: '14:00', end: '18:00' }],
    friday: [{ start: '08:00', end: '12:00' }, { start: '14:00', end: '18:00' }],
    saturday: [{ start: '08:00', end: '13:00' }],
    sunday: [],
  };
  const [workingHours, setWorkingHours] = useState<WeeklyWorkingHours>(defaultHours);

  // Helper notice
  const notify = (type: 'success' | 'error', message: string) => {
    setFeedback({ type, message });
    setTimeout(() => setFeedback(null), 5000);
  };

  // Handlers for Shifts
  const addShift = (day: string) => {
    setWorkingHours((prev) => {
      const current = prev[day] || [];
      return {
        ...prev,
        [day]: [...current, { start: '09:00', end: '17:00' }],
      };
    });
  };

  const removeShift = (day: string, idx: number) => {
    setWorkingHours((prev) => {
      const current = prev[day] || [];
      return {
        ...prev,
        [day]: current.filter((_, i) => i !== idx),
      };
    });
  };

  const updateShift = (day: string, idx: number, field: 'start' | 'end', val: string) => {
    setWorkingHours((prev) => {
      const current = [...(prev[day] || [])];
      if (current[idx]) {
        current[idx] = { ...current[idx], [field]: val };
      }
      return { ...prev, [day]: current };
    });
  };

  const handleSyncCalCom = async () => {
    setIsSyncing(true);
    const res = await syncCalComProviderAction();
    setIsSyncing(false);
    if (res.ok) {
      const { event_types = 0, schedules = 0, teams = 0 } = res.data.counts;
      notify(
        'success',
        `Sincronización Cal.com completada: ${event_types} tipos de cita, ${schedules} horarios, ${teams} equipos.`
      );
      const [schRes, etRes] = await Promise.all([fetchSchedulesAction(), fetchEventTypesAction()]);
      if (schRes.ok) {
        setSchedules(schRes.data);
        if (schRes.data.length > 0 && !selectedScheduleId) {
          setSelectedScheduleId(schRes.data[0].id);
        }
      }
      if (etRes.ok) setEventTypes(etRes.data);
    } else {
      notify('error', `Error al sincronizar con Cal.com: ${res.detail}`);
    }
  };

  const handleOpenCreateEventType = () => {
    setEditingEventTypeId(null);
    setEventTypeForm({
      name: '',
      slug: '',
      description: '',
      duration_minutes: config.default_duration_minutes || 30,
      slot_interval_minutes: config.slot_interval_minutes || 30,
      buffer_before_minutes: config.buffer_before_minutes || 0,
      buffer_after_minutes: config.buffer_after_minutes || 0,
      minimum_notice_minutes: config.minimum_notice_minutes || 60,
      local_schedule_id: schedules.length > 0 ? schedules[0].id : '',
      local_team_id: teams.length > 0 ? teams[0].id : '',
      is_active: true,
    });
    setShowEventTypeModal(true);
  };

  const handleOpenEditEventType = (et: SchedulingEventType) => {
    setEditingEventTypeId(et.id);
    setEventTypeForm({
      name: et.name,
      slug: et.slug,
      description: et.description || '',
      duration_minutes: et.duration_minutes,
      slot_interval_minutes: et.slot_interval_minutes,
      buffer_before_minutes: et.buffer_before_minutes,
      buffer_after_minutes: et.buffer_after_minutes,
      minimum_notice_minutes: et.minimum_notice_minutes,
      local_schedule_id: et.local_schedule_id || '',
      local_team_id: et.local_team_id || '',
      is_active: et.is_active,
    });
    setShowEventTypeModal(true);
  };

  const handleSaveEventType = async (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const payload: SchedulingEventTypeCreateRequest = {
        name: eventTypeForm.name,
        slug: eventTypeForm.slug,
        description: eventTypeForm.description || undefined,
        duration_minutes: Number(eventTypeForm.duration_minutes),
        slot_interval_minutes: Number(eventTypeForm.slot_interval_minutes),
        buffer_before_minutes: Number(eventTypeForm.buffer_before_minutes),
        buffer_after_minutes: Number(eventTypeForm.buffer_after_minutes),
        minimum_notice_minutes: Number(eventTypeForm.minimum_notice_minutes),
        local_schedule_id: eventTypeForm.local_schedule_id || undefined,
        local_team_id: eventTypeForm.local_team_id || undefined,
        is_active: eventTypeForm.is_active,
      };

      if (editingEventTypeId) {
        const res = await updateEventTypeAction(editingEventTypeId, payload);
        if (res.ok) {
          setEventTypes((prev) => prev.map((item) => (item.id === editingEventTypeId ? res.data : item)));
          setShowEventTypeModal(false);
          notify('success', `Tipo de cita "${res.data.name}" actualizado.`);
        } else {
          notify('error', `Error al actualizar: ${res.detail}`);
        }
      } else {
        const res = await createEventTypeAction(payload);
        if (res.ok) {
          setEventTypes((prev) => [...prev, res.data]);
          setShowEventTypeModal(false);
          notify('success', `Tipo de cita "${res.data.name}" creado.`);
        } else {
          notify('error', `Error al crear: ${res.detail}`);
        }
      }
    });
  };

  const handleDeleteEventType = async (id: string, name: string) => {
    if (!confirm(`¿Eliminar tipo de cita "${name}"?`)) return;
    startTransition(async () => {
      const res = await deleteEventTypeAction(id);
      if (res.ok) {
        setEventTypes((prev) => prev.filter((et) => et.id !== id));
        notify('success', `Tipo de cita "${name}" eliminado.`);
      } else {
        notify('error', `Error al eliminar: ${res.detail}`);
      }
    });
  };

  const handleCreateSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const res = await createScheduleAction(scheduleForm);
      if (res.ok) {
        setSchedules((prev) => [...prev, res.data]);
        setSelectedScheduleId(res.data.id);
        setShowScheduleModal(false);
        setScheduleForm({ name: '', timezone: config.timezone, is_default: false });
        notify('success', `Perfil de horario "${res.data.name}" creado.`);
      } else {
        notify('error', `Error al crear horario: ${res.detail}`);
      }
    });
  };

  const handleDeleteSchedule = async (id: string, name: string) => {
    if (!confirm(`¿Eliminar perfil de horario "${name}"?`)) return;
    startTransition(async () => {
      const res = await deleteScheduleAction(id);
      if (res.ok) {
        setSchedules((prev) => prev.filter((s) => s.id !== id));
        if (selectedScheduleId === id) {
          const remaining = schedules.filter((s) => s.id !== id);
          setSelectedScheduleId(remaining.length > 0 ? remaining[0].id : '');
        }
        notify('success', `Horario "${name}" eliminado.`);
      } else {
        notify('error', `Error al eliminar horario: ${res.detail}`);
      }
    });
  };

  const saveWorkingHours = () => {
    startTransition(async () => {
      if (selectedScheduleId) {
        const res = await updateScheduleAction(selectedScheduleId, { working_hours: workingHours });
        if (res.ok) {
          setSchedules((prev) =>
            prev.map((s) => (s.id === selectedScheduleId ? { ...s, working_hours: workingHours } : s))
          );
          notify('success', 'Horarios guardados en el perfil de disponibilidad.');
          return;
        }
      }
      const res = await updateSchedulingConfigAction({ working_hours_json: workingHours });
      if (res.ok) {
        setConfig(res.data);
        notify('success', 'Horarios semanales guardados exitosamente.');
      } else {
        notify('error', `Error al guardar horarios: ${res.detail}`);
      }
    });
  };


  // Handlers for Rules
  const saveRules = (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const res = await updateSchedulingConfigAction({
        default_duration_minutes: Number(config.default_duration_minutes),
        slot_interval_minutes: Number(config.slot_interval_minutes),
        buffer_before_minutes: Number(config.buffer_before_minutes),
        buffer_after_minutes: Number(config.buffer_after_minutes),
        minimum_notice_minutes: Number(config.minimum_notice_minutes),
        maximum_booking_days: Number(config.maximum_booking_days),
        routing_strategy: config.routing_strategy,
        timezone: config.timezone,
      });
      if (res.ok) {
        setConfig(res.data);
        notify('success', 'Reglas de agendamiento actualizadas con éxito.');
      } else {
        notify('error', `Error al actualizar reglas: ${res.detail}`);
      }
    });
  };

  // Resource Create Handler
  const handleCreateResource = async (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const res = await createSchedulingResourceAction(resForm);
      if (res.ok) {
        setResources((prev) => [...prev, res.data]);
        setShowResourceModal(false);
        setResForm({ name: '', email: '', phone: '', resource_type: 'user', priority: 1, capacity: 1, team: '' });
        notify('success', `Recurso "${res.data.name}" creado con éxito.`);
      } else {
        notify('error', `Error al crear recurso: ${res.detail}`);
      }
    });
  };

  // Resource Delete Handler
  const handleDeleteResource = async (id: string, name: string) => {
    if (!confirm(`¿Eliminar recurso "${name}"?`)) return;
    startTransition(async () => {
      const res = await deleteSchedulingResourceAction(id);
      if (res.ok) {
        setResources((prev) => prev.filter((r) => r.id !== id));
        notify('success', `Recurso "${name}" eliminado.`);
      } else {
        notify('error', `Error al eliminar: ${res.detail}`);
      }
    });
  };

  // Team Create Handler
  const handleCreateTeam = async (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const res = await createSchedulingTeamAction(teamForm);
      if (res.ok) {
        setTeams((prev) => [...prev, res.data]);
        setShowTeamModal(false);
        setTeamForm({ name: '', description: '', routing_strategy: 'round_robin' });
        notify('success', `Equipo "${res.data.name}" creado.`);
      } else {
        notify('error', `Error al crear equipo: ${res.detail}`);
      }
    });
  };

  // Team Delete Handler
  const handleDeleteTeam = async (id: string, name: string) => {
    if (!confirm(`¿Eliminar equipo "${name}"?`)) return;
    startTransition(async () => {
      const res = await deleteSchedulingTeamAction(id);
      if (res.ok) {
        setTeams((prev) => prev.filter((t) => t.id !== id));
        notify('success', `Equipo "${name}" eliminado.`);
      } else {
        notify('error', `Error al eliminar: ${res.detail}`);
      }
    });
  };

  // Add Member to Team
  const handleAddMember = async (teamId: string) => {
    if (!selectedResourceId) return;
    startTransition(async () => {
      const res = await addSchedulingTeamMemberAction(teamId, { resource_id: selectedResourceId });
      if (res.ok) {
        setTeams((prev) =>
          prev.map((t) => (t.id === teamId ? { ...t, members: [...t.members, res.data] } : t))
        );
        setMemberTeamId(null);
        setSelectedResourceId('');
        notify('success', 'Miembro añadido al equipo.');
      } else {
        notify('error', `Error al añadir miembro: ${res.detail}`);
      }
    });
  };

  // Remove Member from Team
  const handleRemoveMember = async (teamId: string, resourceId: string) => {
    startTransition(async () => {
      const res = await removeSchedulingTeamMemberAction(teamId, resourceId);
      if (res.ok) {
        setTeams((prev) =>
          prev.map((t) =>
            t.id === teamId ? { ...t, members: t.members.filter((m) => m.resource_id !== resourceId) } : t
          )
        );
        notify('success', 'Miembro removido del equipo.');
      } else {
        notify('error', `Error al remover miembro: ${res.detail}`);
      }
    });
  };

  // Exception Create Handler
  const handleCreateException = async (e: React.FormEvent) => {
    e.preventDefault();
    startTransition(async () => {
      const payload: Partial<SchedulingAvailabilityException> = {
        exception_date: excForm.exception_date,
        exception_type: excForm.exception_type,
        reason: excForm.reason || undefined,
        resource_id: excForm.resource_id || undefined,
      };
      if (excForm.exception_type === 'custom_hours') {
        payload.start_time = excForm.start_time;
        payload.end_time = excForm.end_time;
      }
      const res = await createSchedulingExceptionAction(payload);
      if (res.ok) {
        setExceptions((prev) => [...prev, res.data]);
        setShowExceptionModal(false);
        setExcForm({
          exception_date: '',
          exception_type: 'unavailable',
          start_time: '08:00',
          end_time: '12:00',
          reason: '',
          resource_id: '',
        });
        notify('success', 'Excepción guardada.');
      } else {
        notify('error', `Error al crear excepción: ${res.detail}`);
      }
    });
  };

  // Exception Delete Handler
  const handleDeleteException = async (id: string) => {
    startTransition(async () => {
      const res = await deleteSchedulingExceptionAction(id);
      if (res.ok) {
        setExceptions((prev) => prev.filter((e) => e.id !== id));
        notify('success', 'Excepción eliminada.');
      } else {
        notify('error', `Error al eliminar: ${res.detail}`);
      }
    });
  };

  // Agent Config Save Handler
  const handleSaveAgentConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!agentForm.agent_id) {
      notify('error', 'El ID del agente es obligatorio.');
      return;
    }
    startTransition(async () => {
      const isEventType = agentForm.target_type === 'event_type';
      const selectedEt = isEventType ? eventTypes.find((e) => e.id === agentForm.target_id) : null;
      const payload = {
        provider: isEventType ? selectedEt?.provider || 'calcom' : 'google_calendar',
        routing_strategy: agentForm.target_type,
        event_type_id: isEventType ? agentForm.target_id || undefined : undefined,
        team_id: agentForm.target_type === 'team' ? agentForm.target_id || undefined : undefined,
        resource_id: agentForm.target_type === 'resource' ? agentForm.target_id || undefined : undefined,
        duration_minutes: Number(agentForm.duration_minutes),
        allow_check_availability: agentForm.allow_check_availability,
        allow_create_booking: agentForm.allow_create_booking,
        allow_reschedule: agentForm.allow_reschedule,
        allow_cancel: agentForm.allow_cancel,
        is_active: true,
      };
      const res = await upsertAgentSchedulingConfigAction(agentForm.agent_id, payload);

      if (res.ok) {
        notify('success', `Configuración del agente ${agentForm.agent_id} guardada.`);
      } else {
        notify('error', `Error al guardar configuración: ${res.detail}`);
      }
    });
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground flex items-center gap-2">
            <Calendar className="h-6 w-6 text-primary" />
            Agenda y Disponibilidad
          </h1>
          <p className="text-sm text-muted-foreground">
            Motor de scheduling multi-tenant: calendarios Google, Cal.com (v2), recursos, turnos y reglas de agendamiento.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {providers.some((p) => p.provider === 'calcom') || schedules.some((s) => s.provider === 'calcom') ? (
            <Badge variant="outline" className="border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-600 gap-1.5 py-1">
              <CalendarCheck className="h-3.5 w-3.5" /> Cal.com Activo
            </Badge>
          ) : null}

          {summary.google_connected ? (
            <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 gap-1.5 py-1">
              <CheckCircle2 className="h-3.5 w-3.5" /> Google Calendar Conectado
            </Badge>
          ) : (
            <Link href={`/${locale}/integrations/google-calendar`}>
              <Badge variant="destructive" className="gap-1.5 py-1 cursor-pointer">
                <AlertCircle className="h-3.5 w-3.5" /> Conectar Google Calendar
              </Badge>
            </Link>
          )}

          {canEdit && (providers.some((p) => p.provider === 'calcom') || schedules.some((s) => s.provider === 'calcom')) && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleSyncCalCom}
              disabled={isSyncing}
              className="gap-1 text-xs"
            >
              {isSyncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
              Sincronizar Cal.com
            </Button>
          )}

          <Link href={`/${locale}/integrations/calcom`}>
            <Button variant="outline" size="sm" className="gap-1 text-xs">
              <ExternalLink className="h-3.5 w-3.5" /> Configurar Cal.com
            </Button>
          </Link>
        </div>
      </div>

      {/* Global feedback message */}
      {feedback && (
        <div
          role="alert"
          className={`flex items-center gap-2 rounded-lg border p-3 text-sm transition-all ${
            feedback.type === 'success'
              ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-600'
              : 'border-destructive/30 bg-destructive/10 text-destructive'
          }`}
        >
          {feedback.type === 'success' ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
          {feedback.message}
        </div>
      )}

      {/* Navigation Sub-Tabs */}
      <div className="border-b border-border">
        <nav className="flex space-x-2 overflow-x-auto" aria-label="Secciones de Agenda">
          {[
            { id: 'resumen', label: 'Resumen', icon: Layers },
            { id: 'event_types', label: `Tipos de Cita (${eventTypes.length})`, icon: CalendarDays },
            { id: 'disponibilidad', label: 'Disponibilidad', icon: Clock },
            { id: 'recursos', label: 'Recursos', icon: Users },
            { id: 'equipos', label: 'Equipos (Round Robin)', icon: UserCheck },
            { id: 'reglas', label: 'Reglas y Buffers', icon: Sliders },
            { id: 'excepciones', label: 'Excepciones', icon: Calendar },
            { id: 'agentes', label: 'Agentes IA', icon: Bot },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id as TabKey)}
                className={`flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2.5 text-sm font-medium transition-colors ${
                  active
                    ? 'border-primary text-primary'
                    : 'border-transparent text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>


      {/* =========================================================================
          TAB 1: RESUMEN
      ========================================================================= */}
      {activeTab === 'resumen' && (
        <div className="space-y-6">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Recursos Activos</CardTitle>
                <Users className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.active_resources_count}</div>
                <p className="text-xs text-muted-foreground">Asesores, médicos y consultorios</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Equipos de Enrutamiento</CardTitle>
                <UserCheck className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.teams_count}</div>
                <p className="text-xs text-muted-foreground">Distribución Round Robin activa</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Calendarios Conectados</CardTitle>
                <CalendarDays className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.connected_calendars_count}</div>
                <p className="text-xs text-muted-foreground">Google Calendar sincronizados</p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">Próximas Citas</CardTitle>
                <Clock className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{summary.upcoming_bookings_count}</div>
                <p className="text-xs text-muted-foreground">Reservas programadas en CRM</p>
              </CardContent>
            </Card>
          </div>

          {/* Operational Alerts */}
          {summary.alerts && summary.alerts.length > 0 && (
            <Card className="border-amber-500/30 bg-amber-500/5">
              <CardHeader className="pb-3">
                <CardTitle className="text-base text-amber-600 flex items-center gap-2">
                  <AlertTriangle className="h-5 w-5" /> Alertas Operativas de Agenda
                </CardTitle>
                <CardDescription>
                  Resuelve estas recomendaciones para asegurar que el motor de agendamiento funcione a la perfección:
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2 text-sm text-amber-700 dark:text-amber-300">
                  {summary.alerts.map((alert, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" />
                      {alert}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {/* Quick config overview */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Resumen de Configuración Activa</CardTitle>
              <CardDescription>Parámetros aplicados por defecto a las reservas de este tenant</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3 text-sm">
              <div>
                <span className="text-muted-foreground">Zona Horaria:</span>
                <p className="font-medium text-foreground">{config.timezone}</p>
              </div>
              <div>
                <span className="text-muted-foreground">Duración / Intervalo:</span>
                <p className="font-medium text-foreground">{config.default_duration_minutes} min / cada {config.slot_interval_minutes} min</p>
              </div>
              <div>
                <span className="text-muted-foreground">Buffers (Antes / Después):</span>
                <p className="font-medium text-foreground">{config.buffer_before_minutes} min / {config.buffer_after_minutes} min</p>
              </div>
              <div>
                <span className="text-muted-foreground">Anticipación Mínima:</span>
                <p className="font-medium text-foreground">{config.minimum_notice_minutes} minutos</p>
              </div>
              <div>
                <span className="text-muted-foreground">Ventana Máxima de Reserva:</span>
                <p className="font-medium text-foreground">{config.maximum_booking_days} días</p>
              </div>
              <div>
                <span className="text-muted-foreground">Estrategia por Defecto:</span>
                <p className="font-medium text-foreground capitalize">{config.routing_strategy}</p>
              </div>
            </CardContent>
          </Card>

          {connectedGoogleCalendars && connectedGoogleCalendars.length > 0 && (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base flex items-center gap-2">
                  <CalendarDays className="h-4 w-4 text-sky-500" /> Calendarios Google Sincronizados
                </CardTitle>
                <CardDescription>Cuentas conectadas para validación de FreeBusy y creación de eventos</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {connectedGoogleCalendars.map((c) => (
                    <div key={c.id} className="flex items-center justify-between p-2.5 rounded-md bg-muted/20 text-sm">
                      <div className="flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full bg-emerald-500" />
                        <span className="font-medium text-foreground">{c.summary || c.google_calendar_id}</span>
                      </div>
                      <Badge variant="outline" className="text-xs border-emerald-500/30 text-emerald-600 bg-emerald-500/5">
                        Conectado
                      </Badge>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB: TIPOS DE CITA (EVENT TYPES)
      ========================================================================= */}
      {activeTab === 'event_types' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Tipos de Cita y Eventos</h2>
              <p className="text-sm text-muted-foreground">
                Servicios y formatos de reunión ofrecidos a tus clientes, sincronizados con Cal.com o gestionados por ServiGlobal.
              </p>
            </div>
            <div className="flex items-center gap-2">
              {canEdit && (
                <>
                  <Button
                    variant="outline"
                    onClick={handleSyncCalCom}
                    disabled={isSyncing}
                    className="gap-2 text-xs"
                  >
                    {isSyncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    Sincronizar Cal.com
                  </Button>
                  <Button onClick={handleOpenCreateEventType} className="gap-2">
                    <Plus className="h-4 w-4" /> Nuevo Tipo de Cita
                  </Button>
                </>
              )}
            </div>
          </div>

          {eventTypes.length === 0 ? (
            <Card className="text-center p-8 space-y-3">
              <div className="mx-auto w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary">
                <CalendarDays className="h-6 w-6" />
              </div>
              <div>
                <h3 className="text-base font-semibold text-foreground">No hay tipos de cita registrados</h3>
                <p className="text-sm text-muted-foreground max-w-md mx-auto mt-1">
                  Crea tu primer tipo de cita o sincroniza directamente los existentes en tu cuenta de Cal.com.
                </p>
              </div>
              {canEdit && (
                <div className="flex items-center justify-center gap-2 pt-2">
                  <Button onClick={handleOpenCreateEventType} className="gap-2">
                    <Plus className="h-4 w-4" /> Crear Tipo de Cita
                  </Button>
                  <Button variant="outline" onClick={handleSyncCalCom} disabled={isSyncing} className="gap-2">
                    {isSyncing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                    Sincronizar desde Cal.com
                  </Button>
                </div>
              )}
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                  <tr>
                    <th className="p-3">Nombre y Slug</th>
                    <th className="p-3">Proveedor</th>
                    <th className="p-3">Duración / Intervalo</th>
                    <th className="p-3">Buffers y Aviso</th>
                    <th className="p-3">Horario / Equipo</th>
                    <th className="p-3">Sincronización</th>
                    <th className="p-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {eventTypes.map((et) => {
                    const linkedSchedule = schedules.find((s) => s.id === et.local_schedule_id);
                    const linkedTeam = teams.find((t) => t.id === et.local_team_id);
                    return (
                      <tr key={et.id} className="hover:bg-muted/20">
                        <td className="p-3">
                          <div className="font-medium text-foreground">{et.name}</div>
                          <div className="text-xs text-muted-foreground font-mono">/{et.slug}</div>
                          {et.description && (
                            <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">{et.description}</div>
                          )}
                        </td>
                        <td className="p-3">
                          {et.provider === 'calcom' ? (
                            <Badge variant="outline" className="border-fuchsia-500/30 bg-fuchsia-500/10 text-fuchsia-600">
                              Cal.com
                            </Badge>
                          ) : (
                            <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">
                              Google
                            </Badge>
                          )}
                        </td>
                        <td className="p-3 text-muted-foreground">
                          <div>{et.duration_minutes} min</div>
                          <div className="text-xs text-muted-foreground">cada {et.slot_interval_minutes} min</div>
                        </td>
                        <td className="p-3 text-xs text-muted-foreground">
                          <div>Buffers: +{et.buffer_before_minutes}m / +{et.buffer_after_minutes}m</div>
                          <div>Aviso mín: {et.minimum_notice_minutes}m</div>
                        </td>
                        <td className="p-3 text-xs text-muted-foreground">
                          <div>Horario: <span className="font-medium text-foreground">{linkedSchedule?.name || 'Base del Tenant'}</span></div>
                          <div>Equipo: <span className="font-medium text-foreground">{linkedTeam?.name || 'Sin equipo'}</span></div>
                        </td>
                        <td className="p-3 text-xs">
                          {et.sync_status === 'synced' && (
                            <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600">
                              Sincronizado
                            </Badge>
                          )}
                          {et.sync_status === 'local_only' && (
                            <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-600">
                              Local
                            </Badge>
                          )}
                          {et.sync_status === 'remote_deleted' && (
                            <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600">
                              Eliminado en remoto
                            </Badge>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          {canEdit && (
                            <div className="flex items-center justify-end gap-1">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenEditEventType(et)}
                                className="h-8 w-8 p-0"
                              >
                                <Edit2 className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteEventType(et.id, et.name)}
                                className="text-destructive h-8 w-8 p-0 hover:bg-destructive/10"
                              >
                                <Trash2 className="h-3.5 w-3.5" />
                              </Button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Modal Crear / Editar Tipo de Cita */}
          {showEventTypeModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-lg rounded-lg border border-border bg-card p-6 shadow-xl space-y-4 max-h-[90vh] overflow-y-auto">
                <div className="flex justify-between items-center border-b pb-3">
                  <h3 className="font-semibold text-lg">
                    {editingEventTypeId ? 'Editar Tipo de Cita' : 'Nuevo Tipo de Cita'}
                  </h3>
                  <button
                    onClick={() => setShowEventTypeModal(false)}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleSaveEventType} className="space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="col-span-2">
                      <label className="text-xs font-medium text-muted-foreground">Nombre del Tipo de Cita *</label>
                      <input
                        required
                        type="text"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.name}
                        onChange={(e) => {
                          const val = e.target.value;
                          setEventTypeForm({
                            ...eventTypeForm,
                            name: val,
                            slug: editingEventTypeId
                              ? eventTypeForm.slug
                              : val
                                  .toLowerCase()
                                  .replace(/[^a-z0-9]+/g, '-')
                                  .replace(/(^-|-$)/g, ''),
                          });
                        }}
                        placeholder="Ej: Asesoría Inmobiliaria 30 Minutos"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Slug (URL) *</label>
                      <input
                        required
                        type="text"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm font-mono"
                        value={eventTypeForm.slug}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, slug: e.target.value })}
                        placeholder="asesoria-inmobiliaria"
                      />
                    </div>

                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Duración (minutos) *</label>
                      <input
                        required
                        type="number"
                        min="5"
                        max="480"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.duration_minutes}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, duration_minutes: Number(e.target.value) })}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Descripción</label>
                    <textarea
                      rows={2}
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={eventTypeForm.description || ''}
                      onChange={(e) => setEventTypeForm({ ...eventTypeForm, description: e.target.value })}
                      placeholder="Breve resumen de los temas a tratar en la sesión..."
                    />
                  </div>

                  <div className="grid grid-cols-3 gap-3">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Intervalo (min)</label>
                      <input
                        type="number"
                        min="5"
                        max="480"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.slot_interval_minutes}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, slot_interval_minutes: Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Buffer Antes (min)</label>
                      <input
                        type="number"
                        min="0"
                        max="240"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.buffer_before_minutes}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, buffer_before_minutes: Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Buffer Después (min)</label>
                      <input
                        type="number"
                        min="0"
                        max="240"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.buffer_after_minutes}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, buffer_after_minutes: Number(e.target.value) })}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Horario de Disponibilidad</label>
                      <select
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.local_schedule_id || ''}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, local_schedule_id: e.target.value })}
                      >
                        <option value="">Por defecto (Horario Base)</option>
                        {schedules.map((s) => (
                          <option key={s.id} value={s.id}>
                            {s.name} {s.is_default ? '(Por defecto)' : ''}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Equipo de Asignación</label>
                      <select
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={eventTypeForm.local_team_id || ''}
                        onChange={(e) => setEventTypeForm({ ...eventTypeForm, local_team_id: e.target.value })}
                      >
                        <option value="">Sin equipo (Asignación directa)</option>
                        {teams.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-3 border-t">
                    <Button type="button" variant="outline" onClick={() => setShowEventTypeModal(false)}>
                      Cancelar
                    </Button>
                    <Button type="submit" disabled={isPending}>
                      {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Guardar Tipo de Cita'}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 2: RECURSOS
      ========================================================================= */}
      {activeTab === 'recursos' && (

        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Recursos Agendables</h2>
              <p className="text-sm text-muted-foreground">
                Vendedores, asesores, médicos, salas o consultorios asociados a calendarios Google.
              </p>
            </div>
            {canEdit && (
              <Button onClick={() => setShowResourceModal(true)} className="gap-2">
                <Plus className="h-4 w-4" /> Nuevo Recurso
              </Button>
            )}
          </div>

          {resources.length === 0 ? (
            <Card className="text-center p-8">
              <p className="text-muted-foreground">No hay recursos configurados todavía.</p>
              {canEdit && (
                <Button variant="outline" className="mt-4 gap-2" onClick={() => setShowResourceModal(true)}>
                  <Plus className="h-4 w-4" /> Crear el primer recurso
                </Button>
              )}
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                  <tr>
                    <th className="p-3">Nombre</th>
                    <th className="p-3">Tipo</th>
                    <th className="p-3">Email / Contacto</th>
                    <th className="p-3">Prioridad</th>
                    <th className="p-3">Calendarios Asociados</th>
                    <th className="p-3">Asignaciones</th>
                    <th className="p-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {resources.map((r) => (
                    <tr key={r.id} className="hover:bg-muted/20">
                      <td className="p-3 font-medium text-foreground">
                        {r.name}
                        {r.team && <span className="ml-2 text-xs text-muted-foreground">({r.team})</span>}
                      </td>
                      <td className="p-3 capitalize text-muted-foreground">{r.resource_type}</td>
                      <td className="p-3 text-muted-foreground">
                        <div>{r.email || '—'}</div>
                        <div className="text-xs">{r.phone || ''}</div>
                      </td>
                      <td className="p-3">
                        <Badge variant="outline">{r.priority}</Badge>
                      </td>
                      <td className="p-3 text-xs">
                        {r.calendars && r.calendars.length > 0 ? (
                          <div className="space-y-1">
                            {r.calendars.map((c) => (
                              <div key={c.id} className="flex items-center gap-1.5 text-muted-foreground">
                                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                                {c.summary || c.google_calendar_id}
                                {c.is_destination && <Badge variant="secondary" className="text-[10px] py-0">Destino</Badge>}
                              </div>
                            ))}
                          </div>
                        ) : (
                          <span className="text-amber-500">Sin calendarios</span>
                        )}
                      </td>
                      <td className="p-3 text-muted-foreground">{r.total_assigned_count} citas</td>
                      <td className="p-3 text-right">
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteResource(r.id, r.name)}
                            className="text-destructive hover:bg-destructive/10"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Modal Nuevo Recurso */}
          {showResourceModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl space-y-4">
                <div className="flex justify-between items-center border-b pb-3">
                  <h3 className="font-semibold text-lg">Nuevo Recurso de Agenda</h3>
                  <button onClick={() => setShowResourceModal(false)} className="text-muted-foreground hover:text-foreground">✕</button>
                </div>
                <form onSubmit={handleCreateResource} className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Nombre completo / Sala *</label>
                    <input
                      required
                      type="text"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={resForm.name}
                      onChange={(e) => setResForm({ ...resForm, name: e.target.value })}
                      placeholder="Ej: Dr. Carlos Pérez o Sala A"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Tipo de recurso</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={resForm.resource_type}
                      onChange={(e) => setResForm({ ...resForm, resource_type: e.target.value })}
                    >
                      <option value="user">Usuario / Asesor / Profesional</option>
                      <option value="doctor">Médico / Especialista</option>
                      <option value="room">Consultorio / Sala</option>
                      <option value="equipment">Equipo / Recurso físico</option>
                    </select>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Email</label>
                      <input
                        type="email"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={resForm.email}
                        onChange={(e) => setResForm({ ...resForm, email: e.target.value })}
                        placeholder="asesor@empresa.com"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Teléfono</label>
                      <input
                        type="text"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={resForm.phone}
                        onChange={(e) => setResForm({ ...resForm, phone: e.target.value })}
                        placeholder="+57 300 000 0000"
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Prioridad (1-10)</label>
                      <input
                        type="number"
                        min="1"
                        max="10"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={resForm.priority}
                        onChange={(e) => setResForm({ ...resForm, priority: Number(e.target.value) })}
                      />
                    </div>
                    <div>
                      <label className="text-xs font-medium text-muted-foreground">Equipo / Rol</label>
                      <input
                        type="text"
                        className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                        value={resForm.team}
                        onChange={(e) => setResForm({ ...resForm, team: e.target.value })}
                        placeholder="Ventas, Soporte..."
                      />
                    </div>
                  </div>
                  <div className="flex justify-end gap-2 pt-3 border-t">
                    <Button type="button" variant="outline" onClick={() => setShowResourceModal(false)}>Cancelar</Button>
                    <Button type="submit" disabled={isPending}>
                      {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Guardar Recurso'}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 3: DISPONIBILIDAD Y JORNADAS
      ========================================================================= */}
      {activeTab === 'disponibilidad' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Horarios de Atención Semanales</h2>
              <p className="text-sm text-muted-foreground">
                Configura los turnos laborables por día. Soporta jornadas partidas (mañana y tarde).
              </p>
            </div>
            {canEdit && (
              <Button onClick={saveWorkingHours} disabled={isPending} className="gap-2">
                {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Clock className="h-4 w-4" />}
                Guardar Horarios
              </Button>
            )}
          </div>

          {/* Schedules / Profiles Selector if available */}
          {schedules.length > 0 && (
            <div className="flex flex-col gap-2 rounded-lg border border-border bg-muted/20 p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Perfiles de Horario ({schedules.length})
                </span>
                {canEdit && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowScheduleModal(true)}
                    className="h-7 gap-1 text-xs text-primary"
                  >
                    <Plus className="h-3.5 w-3.5" /> Nuevo Horario
                  </Button>
                )}
              </div>
              <div className="flex flex-wrap gap-2 pt-1">
                {schedules.map((sch) => {
                  const isSelected = sch.id === selectedScheduleId;
                  return (
                    <div
                      key={sch.id}
                      onClick={() => {
                        setSelectedScheduleId(sch.id);
                        if (sch.working_hours && typeof sch.working_hours === 'object') {
                          setWorkingHours(sch.working_hours as WeeklyWorkingHours);
                        }
                      }}
                      className={`flex items-center gap-2 cursor-pointer rounded-md border px-3 py-1.5 text-xs transition ${
                        isSelected
                          ? 'border-primary bg-primary/10 text-primary font-semibold shadow-xs'
                          : 'border-border bg-background text-muted-foreground hover:border-foreground/30 hover:text-foreground'
                      }`}
                    >
                      <span>{sch.name}</span>
                      {sch.is_default && (
                        <span className="rounded bg-primary/20 px-1 py-0.2 text-[10px]">Default</span>
                      )}
                      {sch.provider === 'calcom' && (
                        <span className="rounded bg-fuchsia-500/20 px-1 py-0.2 text-[10px] text-fuchsia-600">
                          Cal.com
                        </span>
                      )}
                      {canEdit && !sch.is_default && isSelected && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSchedule(sch.id, sch.name);
                          }}
                          className="text-muted-foreground hover:text-destructive ml-1"
                        >
                          ✕
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="space-y-3">
            {WEEKDAYS.map((day) => {
              const shifts = workingHours[day.key] || [];
              const hasShifts = shifts.length > 0;
              return (
                <Card key={day.key} className={hasShifts ? 'border-border' : 'border-border/50 bg-muted/10 opacity-75'}>
                  <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">

                    <div className="w-32">
                      <span className="font-semibold text-foreground">{day.label}</span>
                      <p className="text-xs text-muted-foreground">{hasShifts ? `${shifts.length} turno(s)` : 'No laborable'}</p>
                    </div>

                    <div className="flex-1 space-y-2">
                      {shifts.map((shift, idx) => (
                        <div key={idx} className="flex items-center gap-2">
                          <input
                            type="time"
                            className="rounded-md border border-input bg-background p-1.5 text-sm"
                            value={shift.start}
                            onChange={(e) => updateShift(day.key, idx, 'start', e.target.value)}
                            disabled={!canEdit}
                          />
                          <span className="text-muted-foreground text-xs">a</span>
                          <input
                            type="time"
                            className="rounded-md border border-input bg-background p-1.5 text-sm"
                            value={shift.end}
                            onChange={(e) => updateShift(day.key, idx, 'end', e.target.value)}
                            disabled={!canEdit}
                          />
                          {canEdit && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={() => removeShift(day.key, idx)}
                              className="text-destructive h-8 w-8 p-0"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      ))}
                      {shifts.length === 0 && (
                        <span className="text-xs text-muted-foreground italic">Día de descanso (cerrado)</span>
                      )}
                    </div>

                    {canEdit && (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => addShift(day.key)}
                        className="gap-1 text-xs shrink-0"
                      >
                        <Plus className="h-3.5 w-3.5" /> Añadir turno
                      </Button>
                    )}
                  </div>
                </Card>
              );
            })}
          </div>

          {/* Modal Nuevo Perfil de Horario */}
          {showScheduleModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl space-y-4">
                <div className="flex justify-between items-center border-b pb-3">
                  <h3 className="font-semibold text-lg">Nuevo Perfil de Horario</h3>
                  <button onClick={() => setShowScheduleModal(false)} className="text-muted-foreground hover:text-foreground">✕</button>
                </div>
                <form onSubmit={handleCreateSchedule} className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Nombre del Horario *</label>
                    <input
                      required
                      type="text"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={scheduleForm.name}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, name: e.target.value })}
                      placeholder="Ej: Horario Atención Clientes o Turno Especial"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Zona Horaria</label>
                    <input
                      type="text"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={scheduleForm.timezone ?? 'America/Bogota'}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, timezone: e.target.value })}
                      placeholder="America/Bogota"
                    />
                  </div>
                  <label className="flex items-center gap-2 pt-1 text-sm">
                    <input
                      type="checkbox"
                      checked={Boolean(scheduleForm.is_default)}
                      onChange={(e) => setScheduleForm({ ...scheduleForm, is_default: e.target.checked })}
                    />
                    <span>Marcar como horario predeterminado</span>
                  </label>
                  <div className="flex justify-end gap-2 pt-3 border-t">
                    <Button type="button" variant="outline" onClick={() => setShowScheduleModal(false)}>Cancelar</Button>
                    <Button type="submit" disabled={isPending}>
                      {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Crear Horario'}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}


      {/* =========================================================================
          TAB 4: EQUIPOS (ROUND ROBIN)
      ========================================================================= */}
      {activeTab === 'equipos' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Equipos y Round Robin</h2>
              <p className="text-sm text-muted-foreground">
                Agrupa recursos en equipos y distribuye citas equitativamente sin asignar a recursos ocupados.
              </p>
            </div>
            {canEdit && (
              <Button onClick={() => setShowTeamModal(true)} className="gap-2">
                <Plus className="h-4 w-4" /> Crear Equipo
              </Button>
            )}
          </div>

          {teams.length === 0 ? (
            <Card className="text-center p-8">
              <p className="text-muted-foreground">No tienes equipos de agendamiento creados.</p>
              {canEdit && (
                <Button variant="outline" className="mt-4 gap-2" onClick={() => setShowTeamModal(true)}>
                  <Plus className="h-4 w-4" /> Crear un equipo
                </Button>
              )}
            </Card>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              {teams.map((t) => (
                <Card key={t.id} className="border-border">
                  <CardHeader className="pb-3 flex flex-row items-start justify-between">
                    <div>
                      <CardTitle className="text-base">{t.name}</CardTitle>
                      <CardDescription>{t.description || 'Sin descripción'}</CardDescription>
                    </div>
                    {canEdit && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleDeleteTeam(t.id, t.name)}
                        className="text-destructive h-8 w-8 p-0"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex items-center justify-between text-xs text-muted-foreground">
                      <span>Estrategia: <strong className="text-foreground capitalize">{t.routing_strategy}</strong></span>
                      <Badge variant="outline">{t.members.length} miembros</Badge>
                    </div>

                    {/* Members List */}
                    <div className="space-y-2 border-t pt-3">
                      <span className="text-xs font-semibold text-muted-foreground uppercase">Miembros del equipo</span>
                      {t.members.length === 0 ? (
                        <p className="text-xs text-amber-500">Sin miembros asignados.</p>
                      ) : (
                        <div className="space-y-1">
                          {t.members.map((m) => (
                            <div key={m.id} className="flex items-center justify-between rounded-md bg-muted/30 p-2 text-xs">
                              <div>
                                <span className="font-medium text-foreground">{m.resource_name || 'Recurso'}</span>
                                <span className="ml-2 text-muted-foreground">Prioridad {m.priority}</span>
                              </div>
                              {canEdit && (
                                <button
                                  onClick={() => handleRemoveMember(t.id, m.resource_id)}
                                  className="text-muted-foreground hover:text-destructive text-xs"
                                >
                                  ✕
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      )}

                      {canEdit && (
                        <div className="pt-2">
                          {memberTeamId === t.id ? (
                            <div className="flex items-center gap-2">
                              <select
                                className="flex-1 rounded-md border border-input bg-background p-1 text-xs"
                                value={selectedResourceId}
                                onChange={(e) => setSelectedResourceId(e.target.value)}
                              >
                                <option value="">Selecciona recurso...</option>
                                {resources.map((r) => (
                                  <option key={r.id} value={r.id}>{r.name}</option>
                                ))}
                              </select>
                              <Button size="sm" onClick={() => handleAddMember(t.id)} disabled={!selectedResourceId}>
                                Añadir
                              </Button>
                              <Button size="sm" variant="ghost" onClick={() => setMemberTeamId(null)}>
                                Cancelar
                              </Button>
                            </div>
                          ) : (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => {
                                setMemberTeamId(t.id);
                                setSelectedResourceId('');
                              }}
                              className="w-full text-xs gap-1"
                            >
                              <UserPlus className="h-3.5 w-3.5" /> Añadir miembro
                            </Button>
                          )}
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {/* Modal Crear Equipo */}
          {showTeamModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl space-y-4">
                <div className="flex justify-between items-center border-b pb-3">
                  <h3 className="font-semibold text-lg">Nuevo Equipo de Scheduling</h3>
                  <button onClick={() => setShowTeamModal(false)} className="text-muted-foreground hover:text-foreground">✕</button>
                </div>
                <form onSubmit={handleCreateTeam} className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Nombre del equipo *</label>
                    <input
                      required
                      type="text"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={teamForm.name}
                      onChange={(e) => setTeamForm({ ...teamForm, name: e.target.value })}
                      placeholder="Ej: Asesores Inmobiliarios Norte"
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Descripción</label>
                    <textarea
                      rows={2}
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={teamForm.description}
                      onChange={(e) => setTeamForm({ ...teamForm, description: e.target.value })}
                      placeholder="Equipo especializado en propiedades premium..."
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Estrategia de distribución</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={teamForm.routing_strategy}
                      onChange={(e) => setTeamForm({ ...teamForm, routing_strategy: e.target.value })}
                    >
                      <option value="round_robin">Round Robin (Rotación equitativa)</option>
                      <option value="priority">Prioridad estricta</option>
                    </select>
                  </div>
                  <div className="flex justify-end gap-2 pt-3 border-t">
                    <Button type="button" variant="outline" onClick={() => setShowTeamModal(false)}>Cancelar</Button>
                    <Button type="submit" disabled={isPending}>
                      {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Crear Equipo'}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 5: REGLAS Y BUFFERS
      ========================================================================= */}
      {activeTab === 'reglas' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Reglas de Agendamiento</h2>
            <p className="text-sm text-muted-foreground">
              Define duración de citas, pasos entre horarios, tiempos de preparación (buffers) y ventana máxima.
            </p>
          </div>

          <form onSubmit={saveRules} className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Duraciones e Intervalos</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Duración de la cita (minutos)</label>
                  <input
                    type="number"
                    min="5"
                    max="480"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.default_duration_minutes}
                    onChange={(e) => setConfig({ ...config, default_duration_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Tiempo bloqueado en el calendario.</p>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">Intervalo entre horarios ofertados (minutos)</label>
                  <input
                    type="number"
                    min="5"
                    max="480"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.slot_interval_minutes}
                    onChange={(e) => setConfig({ ...config, slot_interval_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Cada cuántos minutos se ofrece un nuevo slot (ej: cada 15 o 30 min).</p>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Buffers de Protección</CardTitle>
                <CardDescription>Evita citas consecutivas dejando tiempo de descanso o preparación.</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Buffer Antes de la Cita (minutos)</label>
                  <input
                    type="number"
                    min="0"
                    max="240"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.buffer_before_minutes}
                    onChange={(e) => setConfig({ ...config, buffer_before_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">Buffer Después de la Cita (minutos)</label>
                  <input
                    type="number"
                    min="0"
                    max="240"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.buffer_after_minutes}
                    onChange={(e) => setConfig({ ...config, buffer_after_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Límites y Zona Horaria</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-3">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">Anticipación Mínima (minutos)</label>
                  <input
                    type="number"
                    min="0"
                    max="10080"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.minimum_notice_minutes}
                    onChange={(e) => setConfig({ ...config, minimum_notice_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Tiempo mínimo entre la reserva y la cita (ej: 60 min).</p>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">Ventana Máxima hacia el Futuro (días)</label>
                  <input
                    type="number"
                    min="1"
                    max="365"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.maximum_booking_days}
                    onChange={(e) => setConfig({ ...config, maximum_booking_days: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Días en adelante que el usuario puede agendar.</p>
                </div>

                <div>
                  <label className="text-xs font-medium text-muted-foreground">Zona Horaria Base</label>
                  <select
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={config.timezone}
                    onChange={(e) => setConfig({ ...config, timezone: e.target.value })}
                    disabled={!canEdit}
                  >
                    <option value="America/Bogota">America/Bogota (GMT-5)</option>
                    <option value="America/Mexico_City">America/Mexico_City (GMT-6)</option>
                    <option value="America/Lima">America/Lima (GMT-5)</option>
                    <option value="America/Santiago">America/Santiago (GMT-4)</option>
                    <option value="America/Buenos_Aires">America/Buenos_Aires (GMT-3)</option>
                    <option value="America/Madrid">Europe/Madrid (GMT+1)</option>
                    <option value="America/New_York">America/New_York (EST)</option>
                  </select>
                </div>
              </CardContent>
            </Card>

            {canEdit && (
              <div className="flex justify-end">
                <Button type="submit" disabled={isPending} className="gap-2">
                  {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sliders className="h-4 w-4" />}
                  Guardar Reglas
                </Button>
              </div>
            )}
          </form>
        </div>
      )}

      {/* =========================================================================
          TAB 6: EXCEPCIONES Y FESTIVOS
      ========================================================================= */}
      {activeTab === 'excepciones' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-foreground">Excepciones de Disponibilidad</h2>
              <p className="text-sm text-muted-foreground">
                Bloquea días festivos, vacaciones o configura horarios especiales para fechas específicas.
              </p>
            </div>
            {canEdit && (
              <Button onClick={() => setShowExceptionModal(true)} className="gap-2">
                <Plus className="h-4 w-4" /> Añadir Excepción
              </Button>
            )}
          </div>

          {exceptions.length === 0 ? (
            <Card className="text-center p-8">
              <p className="text-muted-foreground">No hay excepciones o festivos registrados.</p>
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-border bg-muted/40 text-xs font-semibold text-muted-foreground uppercase">
                  <tr>
                    <th className="p-3">Fecha</th>
                    <th className="p-3">Tipo</th>
                    <th className="p-3">Horario / Restricción</th>
                    <th className="p-3">Motivo</th>
                    <th className="p-3">Aplica a</th>
                    <th className="p-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {exceptions.map((exc) => (
                    <tr key={exc.id} className="hover:bg-muted/20">
                      <td className="p-3 font-medium text-foreground">{exc.exception_date}</td>
                      <td className="p-3">
                        {exc.exception_type === 'unavailable' ? (
                          <Badge variant="destructive">No laborable</Badge>
                        ) : (
                          <Badge variant="secondary">Horario especial</Badge>
                        )}
                      </td>
                      <td className="p-3 text-muted-foreground">
                        {exc.exception_type === 'custom_hours' && exc.start_time && exc.end_time
                          ? `${exc.start_time} - ${exc.end_time}`
                          : 'Día completo bloqueado'}
                      </td>
                      <td className="p-3 text-muted-foreground">{exc.reason || '—'}</td>
                      <td className="p-3 text-xs text-muted-foreground">
                        {exc.resource_name ? `Recurso: ${exc.resource_name}` : 'Global (Todos)'}
                      </td>
                      <td className="p-3 text-right">
                        {canEdit && (
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteException(exc.id)}
                            className="text-destructive hover:bg-destructive/10"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Modal Nueva Excepción */}
          {showExceptionModal && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
              <div className="w-full max-w-md rounded-lg border border-border bg-card p-6 shadow-xl space-y-4">
                <div className="flex justify-between items-center border-b pb-3">
                  <h3 className="font-semibold text-lg">Nueva Excepción de Agenda</h3>
                  <button onClick={() => setShowExceptionModal(false)} className="text-muted-foreground hover:text-foreground">✕</button>
                </div>
                <form onSubmit={handleCreateException} className="space-y-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Fecha *</label>
                    <input
                      required
                      type="date"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={excForm.exception_date}
                      onChange={(e) => setExcForm({ ...excForm, exception_date: e.target.value })}
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Tipo de excepción</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={excForm.exception_type}
                      onChange={(e) => setExcForm({ ...excForm, exception_type: e.target.value as 'unavailable' | 'custom_hours' })}
                    >
                      <option value="unavailable">Día no laborable (Bloquear completamente)</option>
                      <option value="custom_hours">Horario especial para este día</option>
                    </select>
                  </div>
                  {excForm.exception_type === 'custom_hours' && (
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">Hora inicio</label>
                        <input
                          type="time"
                          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                          value={excForm.start_time}
                          onChange={(e) => setExcForm({ ...excForm, start_time: e.target.value })}
                        />
                      </div>
                      <div>
                        <label className="text-xs font-medium text-muted-foreground">Hora fin</label>
                        <input
                          type="time"
                          className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                          value={excForm.end_time}
                          onChange={(e) => setExcForm({ ...excForm, end_time: e.target.value })}
                        />
                      </div>
                    </div>
                  )}
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Motivo</label>
                    <input
                      type="text"
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={excForm.reason}
                      onChange={(e) => setExcForm({ ...excForm, reason: e.target.value })}
                      placeholder="Ej: Festivo Nacional, Vacaciones..."
                    />
                  </div>
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Aplica a</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={excForm.resource_id}
                      onChange={(e) => setExcForm({ ...excForm, resource_id: e.target.value })}
                    >
                      <option value="">Global (Todos los recursos)</option>
                      {resources.map((r) => (
                        <option key={r.id} value={r.id}>Solo recurso: {r.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex justify-end gap-2 pt-3 border-t">
                    <Button type="button" variant="outline" onClick={() => setShowExceptionModal(false)}>Cancelar</Button>
                    <Button type="submit" disabled={isPending}>
                      {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Guardar Excepción'}
                    </Button>
                  </div>
                </form>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 7: AGENTES IA
      ========================================================================= */}
      {activeTab === 'agentes' && (
        <div className="space-y-6">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Asignación de Agentes de Voz y Chat</h2>
            <p className="text-sm text-muted-foreground">
              Configura a qué equipo o recurso asigna citas cada agente de IA cuando atiende llamadas o chats.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Vincular Agente a Calendario o Equipo</CardTitle>
              <CardDescription>
                Cuando un agente de IA interactúa en una llamada, consultará disponibilidad y creará la reserva según estas reglas.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSaveAgentConfig} className="space-y-4 max-w-xl">
                <div>
                  <label className="text-xs font-medium text-muted-foreground">ID del Agente (External Agent ID / Ultravox ID) *</label>
                  <input
                    required
                    type="text"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={agentForm.agent_id}
                    onChange={(e) => setAgentForm({ ...agentForm, agent_id: e.target.value })}
                    placeholder="Ej: agent_voice_inmobiliario"
                    disabled={!canEdit}
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Tipo de Asignación</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={agentForm.target_type}
                      onChange={(e) => setAgentForm({ ...agentForm, target_type: e.target.value, target_id: '' })}
                      disabled={!canEdit}
                    >
                      <option value="event_type">Tipo de Cita (Cal.com / Google)</option>
                      <option value="team">Equipo (Round Robin)</option>
                      <option value="resource">Recurso Específico</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-xs font-medium text-muted-foreground">Destino</label>
                    <select
                      className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                      value={agentForm.target_id}
                      onChange={(e) => {
                        const nextId = e.target.value;
                        setAgentForm((prev) => {
                          let nextDuration = prev.duration_minutes;
                          if (prev.target_type === 'event_type') {
                            const found = eventTypes.find((et) => et.id === nextId);
                            if (found) nextDuration = found.duration_minutes;
                          }
                          return { ...prev, target_id: nextId, duration_minutes: nextDuration };
                        });
                      }}
                      disabled={!canEdit}
                    >
                      <option value="">Selecciona destino...</option>
                      {agentForm.target_type === 'event_type'
                        ? eventTypes.map((et) => (
                            <option key={et.id} value={et.id}>
                              {et.name} ({et.duration_minutes} min - {et.provider === 'calcom' ? 'Cal.com' : 'Google'})
                            </option>
                          ))
                        : agentForm.target_type === 'team'
                        ? teams.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.name}
                            </option>
                          ))
                        : resources.map((r) => (
                            <option key={r.id} value={r.id}>
                              {r.name}
                            </option>
                          ))}
                    </select>
                  </div>
                </div>


                <div>
                  <label className="text-xs font-medium text-muted-foreground">Duración de la llamada / cita (minutos)</label>
                  <input
                    type="number"
                    min="5"
                    max="480"
                    className="mt-1 w-full rounded-md border border-input bg-background p-2 text-sm"
                    value={agentForm.duration_minutes}
                    onChange={(e) => setAgentForm({ ...agentForm, duration_minutes: Number(e.target.value) })}
                    disabled={!canEdit}
                  />
                </div>

                <div className="space-y-2 pt-2 border-t">
                  <span className="text-xs font-semibold text-muted-foreground uppercase">Capacidades del Agente</span>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={agentForm.allow_check_availability}
                        onChange={(e) => setAgentForm({ ...agentForm, allow_check_availability: e.target.checked })}
                        disabled={!canEdit}
                      />
                      <span>Consultar disponibilidad</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={agentForm.allow_create_booking}
                        onChange={(e) => setAgentForm({ ...agentForm, allow_create_booking: e.target.checked })}
                        disabled={!canEdit}
                      />
                      <span>Crear citas</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={agentForm.allow_reschedule}
                        onChange={(e) => setAgentForm({ ...agentForm, allow_reschedule: e.target.checked })}
                        disabled={!canEdit}
                      />
                      <span>Reprogramar citas</span>
                    </label>
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={agentForm.allow_cancel}
                        onChange={(e) => setAgentForm({ ...agentForm, allow_cancel: e.target.checked })}
                        disabled={!canEdit}
                      />
                      <span>Cancelar citas</span>
                    </label>
                  </div>
                </div>

                {canEdit && (
                  <Button type="submit" disabled={isPending} className="gap-2 mt-4">
                    {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bot className="h-4 w-4" />}
                    Guardar Configuración de Agente
                  </Button>
                )}
              </form>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
