'use client';

import { useState, type FormEvent } from 'react';
import { AlertCircle, Building2, Mail, Pencil, Phone, User } from 'lucide-react';
import type { LeadDetailResponse, LeadUpdateRequest } from '@/types/crm';
import { canEditLead } from '@/lib/permissions/crm';
import { Button } from '@/components/ui/button';

type Props = { lead: LeadDetailResponse; onSave: (payload: LeadUpdateRequest) => Promise<void>; userRole?: string };
type FieldConfig = { key: keyof LeadUpdateRequest; label: string; type?: 'text' | 'number' | 'select' | 'textarea'; options?: Array<[string, string]> };

const QUALIFICATION_FIELDS: FieldConfig[] = [
  { key: 'interest', label: 'Interés' }, { key: 'industry', label: 'Industria' },
  { key: 'use_case', label: 'Caso de uso' }, { key: 'volume', label: 'Volumen' },
  { key: 'pain_point', label: 'Dolor principal', type: 'textarea' }, { key: 'budget_range', label: 'Presupuesto' },
  { key: 'intent_level', label: 'Nivel de intención' }, { key: 'lead_score', label: 'Lead score', type: 'number' },
];
const MANAGEMENT_FIELDS: FieldConfig[] = [
  { key: 'next_action', label: 'Próxima acción', type: 'textarea' },
  { key: 'status', label: 'Estado', type: 'select', options: [['open', 'Abierto'], ['won', 'Ganado'], ['lost', 'Perdido'], ['unqualified', 'Descalificado'], ['paused', 'Pausado']] },
  { key: 'source', label: 'Origen' }, { key: 'campaign', label: 'Campaña' },
];

export function CrmLeadDetailPanel({ lead, onSave, userRole }: Props) {
  const canEdit = canEditLead(userRole);
  return (
    <div className="space-y-5">
      <section className="rounded-xl border border-border bg-card p-4 sm:p-6">
        <h2 className="border-b border-border pb-3 text-sm font-semibold">Contacto</h2>
        <div className="mt-4 grid gap-4 sm:grid-cols-2">
          <ContactField icon={User} label="Nombre" value={lead.contact.name} />
          <ContactField icon={Building2} label="Empresa" value={lead.contact.company} />
          <ContactField icon={Phone} label="Teléfono" value={lead.contact.phone} />
          <ContactField icon={Mail} label="Correo" value={lead.contact.email} />
        </div>
        <p className="mt-4 text-xs text-muted-foreground">Los datos de contacto son de solo lectura en el contrato actual.</p>
      </section>
      <LeadSectionEditor key={`qualification-${lead.updated_at}`} title="Calificación" fields={QUALIFICATION_FIELDS} lead={lead} canEdit={canEdit} onSave={onSave} />
      <LeadSectionEditor key={`management-${lead.updated_at}`} title="Gestión comercial" fields={MANAGEMENT_FIELDS} lead={lead} canEdit={canEdit} onSave={onSave} />
    </div>
  );
}

function LeadSectionEditor({ title, fields, lead, canEdit, onSave }: { title: string; fields: FieldConfig[]; lead: LeadDetailResponse; canEdit: boolean; onSave: Props['onSave'] }) {
  const initial = Object.fromEntries(fields.map(({ key }) => [key, lead[key as keyof LeadDetailResponse] ?? ''])) as Record<string, string | number>;
  const [values, setValues] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const cancel = () => { setValues(initial); setError(null); setSaved(false); setEditing(false); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setSaved(false);
    const payload: LeadUpdateRequest = {};
    for (const field of fields) {
      const raw = values[field.key];
      if (field.key === 'lead_score') {
        if (raw === '') payload.lead_score = null;
        else {
          const score = Number(raw);
          if (!Number.isInteger(score) || score < 0 || score > 100) { setError('El Lead Score debe ser un entero entre 0 y 100.'); return; }
          payload.lead_score = score;
        }
      } else {
        const value = String(raw).trim();
        (payload as Record<string, string | null>)[field.key] = value || null;
      }
    }
    if (payload.status && !['open', 'won', 'lost', 'unqualified', 'paused'].includes(payload.status)) { setError('Estado no válido.'); return; }
    setSubmitting(true);
    try { await onSave(payload); setSaved(true); setEditing(false); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'No fue posible guardar la sección.'); }
    finally { setSubmitting(false); }
  };

  return (
    <section className="rounded-xl border border-border bg-card p-4 sm:p-6">
      <div className="flex items-center justify-between gap-3 border-b border-border pb-3">
        <h2 className="text-sm font-semibold">{title}</h2>
        {!editing && canEdit ? <Button type="button" variant="outline" size="sm" onClick={() => { setSaved(false); setEditing(true); }}><Pencil className="mr-2 size-3.5" />Editar</Button> : null}
      </div>
      {saved ? <p className="mt-4 text-sm text-emerald-600 dark:text-emerald-400" role="status">Sección guardada correctamente.</p> : null}
      {editing ? (
        <form onSubmit={submit} className="mt-4 space-y-4">
          {error ? <p className="flex gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"><AlertCircle className="mt-0.5 size-4 shrink-0" />{error}</p> : null}
          <div className="grid gap-4 sm:grid-cols-2">{fields.map((field) => <EditableField key={field.key} field={field} value={values[field.key]} disabled={submitting} onChange={(value) => setValues((current) => ({ ...current, [field.key]: value }))} />)}</div>
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end"><Button type="button" variant="outline" onClick={cancel} disabled={submitting}>Cancelar</Button><Button type="submit" disabled={submitting}>{submitting ? 'Guardando…' : 'Guardar sección'}</Button></div>
        </form>
      ) : (
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">{fields.map((field) => <div key={field.key}><dt className="text-xs font-medium text-muted-foreground">{field.label}</dt><dd className="mt-1 whitespace-pre-wrap break-words text-sm">{formatValue(field, initial[field.key])}</dd></div>)}</dl>
      )}
    </section>
  );
}

function EditableField({ field, value, disabled, onChange }: { field: FieldConfig; value: string | number; disabled: boolean; onChange: (value: string) => void }) {
  const id = `lead-${field.key}`;
  const className = 'min-h-10 w-full rounded-md border border-input bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50';
  return <label htmlFor={id} className={field.type === 'textarea' ? 'space-y-1 sm:col-span-2' : 'space-y-1'}><span className="text-xs font-medium text-muted-foreground">{field.label}</span>{field.type === 'select' ? <select id={id} value={String(value)} disabled={disabled} onChange={(event) => onChange(event.target.value)} className={className}>{field.options?.map(([option, label]) => <option key={option} value={option}>{label}</option>)}</select> : field.type === 'textarea' ? <textarea id={id} rows={4} value={String(value)} disabled={disabled} onChange={(event) => onChange(event.target.value)} className={`${className} py-2`} /> : <input id={id} type={field.type ?? 'text'} min={field.type === 'number' ? 0 : undefined} max={field.type === 'number' ? 100 : undefined} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} className={className} />}</label>;
}

function formatValue(field: FieldConfig, value: string | number) { if (value === '') return 'Sin registrar'; return field.options?.find(([option]) => option === value)?.[1] ?? value; }
function ContactField({ icon: Icon, label, value }: { icon: typeof User; label: string; value?: string | null }) { return <div className="flex min-w-0 items-start gap-3"><span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary"><Icon className="size-4" /></span><div className="min-w-0"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 break-words text-sm">{value || 'Sin registrar'}</p></div></div>; }
