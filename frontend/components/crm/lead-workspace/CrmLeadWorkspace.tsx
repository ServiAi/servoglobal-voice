'use client';

import { useRef, useState, type KeyboardEvent } from 'react';
import Link from 'next/link';
import { ArrowLeft, CalendarClock, MessageSquare, Phone, Sparkles } from 'lucide-react';
import type { LeadDetailResponse, LeadUpdateRequest } from '@/types/crm';
import { CrmStageBadge } from '@/components/crm/shared/CrmStageBadge';
import { CrmStatusBadge } from '@/components/crm/shared/CrmStatusBadge';
import { CrmLeadDetailPanel } from '@/components/crm/CrmLeadDetailPanel';
import { CrmLeadQuickActions } from '@/components/crm/CrmLeadQuickActions';
import { CrmActivityTimeline } from '@/components/crm/CrmActivityTimeline';
import { CrmTaskList } from '@/components/crm/CrmTaskList';
import { CrmTaskForm } from '@/components/crm/CrmTaskForm';
import { CrmNoteForm } from '@/components/crm/CrmNoteForm';
import { formatCrmDate, formatDuration } from './crm-format';

type WorkspaceProps = {
  lead: LeadDetailResponse;
  accessToken: string;
  locale: string;
  userRole?: string;
  onSave: (payload: LeadUpdateRequest) => Promise<void>;
  onAddNote: (note: string) => Promise<void>;
  onCreateTask: (payload: { title: string; description?: string; due_at?: string; priority: string }) => Promise<void>;
  onToggleTask: (taskId: string, status: string) => Promise<void>;
  onDeleteTask: (taskId: string) => Promise<void>;
};

const TABS = [
  ['summary', 'Resumen'],
  ['conversations', 'Conversaciones'],
  ['activity', 'Actividad'],
  ['tasks', 'Tareas'],
  ['data', 'Datos'],
] as const;

type TabId = (typeof TABS)[number][0];

export function CrmLeadWorkspace(props: WorkspaceProps) {
  const { lead, accessToken, locale, userRole } = props;
  const [activeTab, setActiveTab] = useState<TabId>('summary');
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next = index;
    if (event.key === 'ArrowRight') next = (index + 1) % TABS.length;
    else if (event.key === 'ArrowLeft') next = (index - 1 + TABS.length) % TABS.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = TABS.length - 1;
    else return;
    event.preventDefault();
    setActiveTab(TABS[next][0]);
    tabRefs.current[next]?.focus();
  };

  return (
    <div className="space-y-5">
      <Link href={`/${locale}/crm/leads`} className="inline-flex min-h-10 items-center gap-2 rounded-md text-sm font-medium text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring">
        <ArrowLeft className="size-4" /> Volver a Leads
      </Link>

      <header className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-6">
        <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              <CrmStageBadge stageKey={lead.stage.key} stageName={lead.stage.name} />
              <CrmStatusBadge status={lead.status} />
              {lead.lead_score !== null && lead.lead_score !== undefined ? (
                <span className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-semibold">Score {lead.lead_score}</span>
              ) : null}
            </div>
            <div>
              <h1 className="break-words text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">{lead.contact.name}</h1>
              {lead.contact.company ? <p className="mt-1 break-words text-sm text-muted-foreground">{lead.contact.company}</p> : null}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              {lead.source ? <span>Origen: {lead.source}</span> : null}
              {lead.campaign ? <span>Campaña: {lead.campaign}</span> : null}
              <span>Actualizado {formatCrmDate(lead.updated_at)}</span>
            </div>
          </div>
          <div className="w-full xl:max-w-xl">
            <CrmLeadQuickActions leadId={lead.id} accessToken={accessToken} currentStageKey={lead.stage.key} contactName={lead.contact.name} contactPhone={lead.contact.phone} userRole={userRole} />
          </div>
        </div>

        <div className="mt-5 rounded-lg border border-primary/20 bg-primary/5 p-4">
          <div className="flex items-start gap-3">
            <CalendarClock className="mt-0.5 size-5 shrink-0 text-primary" />
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-primary">Próxima acción</p>
              <p className="mt-1 whitespace-pre-wrap break-words text-sm font-medium text-foreground">{lead.next_action || 'Requiere definición.'}</p>
            </div>
          </div>
        </div>
      </header>

      <div className="overflow-x-auto border-b border-border" role="tablist" aria-label="Secciones del lead">
        <div className="flex min-w-max gap-1">
          {TABS.map(([id, label], index) => (
            <button key={id} ref={(node) => { tabRefs.current[index] = node; }} id={`lead-tab-${id}`} type="button" role="tab" aria-selected={activeTab === id} aria-controls={`lead-panel-${id}`} tabIndex={activeTab === id ? 0 : -1} onClick={() => setActiveTab(id)} onKeyDown={(event) => handleTabKeyDown(event, index)} className="min-h-10 border-b-2 border-transparent px-4 text-sm font-medium text-muted-foreground outline-none transition hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring aria-selected:border-primary aria-selected:text-foreground">
              {label}
            </button>
          ))}
        </div>
      </div>

      <section id={`lead-panel-${activeTab}`} role="tabpanel" aria-labelledby={`lead-tab-${activeTab}`} tabIndex={0} className="outline-none focus-visible:ring-2 focus-visible:ring-ring">
        {activeTab === 'summary' ? <SummaryTab lead={lead} onOpenData={() => setActiveTab('data')} /> : null}
        {activeTab === 'conversations' ? <ConversationsTab lead={lead} /> : null}
        {activeTab === 'activity' ? <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]"><CrmActivityTimeline activities={lead.activities} /><CrmNoteForm onSubmit={props.onAddNote} userRole={userRole} /></div> : null}
        {activeTab === 'tasks' ? <div className="grid gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]"><div className="rounded-xl border border-border bg-card p-4 sm:p-6"><CrmTaskList tasks={lead.tasks} onToggleStatus={props.onToggleTask} onDelete={props.onDeleteTask} locale={locale} userRole={userRole} /></div><CrmTaskForm onSubmit={props.onCreateTask} userRole={userRole} /></div> : null}
        {activeTab === 'data' ? <CrmLeadDetailPanel lead={lead} onSave={props.onSave} userRole={userRole} /> : null}
      </section>
    </div>
  );
}

function SummaryTab({ lead, onOpenData }: { lead: LeadDetailResponse; onOpenData: () => void }) {
  const commercial = [
    ['Interés', lead.interest], ['Industria', lead.industry], ['Caso de uso', lead.use_case],
    ['Volumen', lead.volume], ['Dolor principal', lead.pain_point], ['Presupuesto', lead.budget_range], ['Nivel de intención', lead.intent_level],
  ] as const;
  const missing = commercial.filter(([, value]) => !value).map(([label]) => label.toLocaleLowerCase('es'));
  return (
    <div className="grid gap-5 lg:grid-cols-3">
      <div className="space-y-5 lg:col-span-2">
        <WorkspaceCard title="Contexto comercial">
          <dl className="grid gap-4 sm:grid-cols-2">
            {commercial.map(([label, value]) => <Field key={label} label={label} value={value} />)}
          </dl>
        </WorkspaceCard>
        <WorkspaceCard title="Resumen de IA" icon={<Sparkles className="size-4 text-primary" />}>
          {lead.short_summary || lead.summary ? <div className="space-y-4"><LongText label="Resumen corto" value={lead.short_summary} /><LongText label="Resumen completo" value={lead.summary} /></div> : <EmptyState text="No hay un resumen disponible para este lead." />}
        </WorkspaceCard>
      </div>
      <div className="space-y-5">
        <WorkspaceCard title="Seguimiento">
          <dl className="space-y-4"><Field label="Estado" value={lead.status} /><Field label="Etapa" value={lead.stage.name} /><Field label="Origen" value={lead.source} /><Field label="Campaña" value={lead.campaign} /><Field label="Creado" value={formatCrmDate(lead.created_at)} /><Field label="Actualizado" value={formatCrmDate(lead.updated_at)} /></dl>
          <button type="button" onClick={onOpenData} className="mt-5 min-h-10 w-full rounded-md border border-border px-4 text-sm font-medium hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Editar datos</button>
        </WorkspaceCard>
        <WorkspaceCard title="Datos faltantes">
          <p className="text-sm text-muted-foreground">{missing.length ? `Faltan ${new Intl.ListFormat('es', { style: 'long', type: 'conjunction' }).format(missing)}.` : 'Los datos comerciales principales están completos.'}</p>
        </WorkspaceCard>
      </div>
    </div>
  );
}

function ConversationsTab({ lead }: { lead: LeadDetailResponse }) {
  const calls = lead.activities.filter((activity) => activity.call_id || activity.activity_type.toLowerCase().includes('call') || activity.activity_type.toLowerCase().includes('llamada'));
  if (!calls.length) return <WorkspaceCard title="Conversaciones"><EmptyState text="No hay llamadas asociadas a este lead." /></WorkspaceCard>;
  return <div className="space-y-3">{calls.map((call) => <article key={call.id} className="rounded-xl border border-border bg-card p-4 sm:p-5"><div className="flex items-start justify-between gap-4"><div className="flex min-w-0 items-start gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"><Phone className="size-4" /></span><div className="min-w-0"><h3 className="break-words text-sm font-semibold">{call.title}</h3><p className="mt-1 text-xs text-muted-foreground">{formatCrmDate(call.occurred_at)}</p></div></div>{call.normalized_status ? <span className="rounded-full border border-border px-2 py-1 text-xs capitalize">{call.normalized_status}</span> : null}</div>{call.description ? <p className="mt-4 whitespace-pre-wrap break-words text-sm text-muted-foreground">{call.description}</p> : null}<div className="mt-4 flex flex-wrap gap-3 text-xs text-muted-foreground">{formatDuration(call.duration_seconds) ? <span>Duración: {formatDuration(call.duration_seconds)}</span> : null}{call.outcome ? <span>Resultado: {call.outcome}</span> : null}</div>{call.summary || call.short_summary ? <LongText label="Resumen" value={call.summary || call.short_summary} /> : null}{call.recording_url ? <audio controls preload="none" src={call.recording_url} className="mt-4 h-10 w-full" /> : null}</article>)}</div>;
}

function WorkspaceCard({ title, icon, children }: { title: string; icon?: React.ReactNode; children: React.ReactNode }) { return <section className="rounded-xl border border-border bg-card p-4 shadow-xs sm:p-6"><div className="mb-4 flex items-center gap-2 border-b border-border pb-3">{icon}<h2 className="text-sm font-semibold">{title}</h2></div>{children}</section>; }
function Field({ label, value }: { label: string; value?: string | number | null }) { return <div className="min-w-0"><dt className="text-xs font-medium text-muted-foreground">{label}</dt><dd className="mt-1 whitespace-pre-wrap break-words text-sm text-foreground">{value === null || value === undefined || value === '' ? 'Sin registrar' : value}</dd></div>; }
function LongText({ label, value }: { label: string; value?: string | null }) { if (!value) return null; return <details open={value.length < 320} className="group mt-4"><summary className="cursor-pointer text-xs font-semibold text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">{label}</summary><p className="mt-2 max-w-prose whitespace-pre-wrap break-words text-sm leading-6 text-foreground">{value}</p></details>; }
function EmptyState({ text }: { text: string }) { return <div className="rounded-lg border border-dashed border-border p-8 text-center"><MessageSquare className="mx-auto size-5 text-muted-foreground" /><p className="mt-2 text-sm text-muted-foreground">{text}</p></div>; }
