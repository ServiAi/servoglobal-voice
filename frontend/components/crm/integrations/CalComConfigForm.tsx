'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { BookingConfigRequest, BookingConfigResponse } from '@/types/crm';
import { configureAdminTenantCalComIntegration, configureCalComIntegration } from '@/lib/api/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  config?: BookingConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: BookingConfigResponse) => void;
  onError: (message: string) => void;
};

const FIELD_CLASS = 'min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

export function CalComConfigForm({ accessToken, config, mode = 'tenant', tenantId, onSaved, onError }: Props) {
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<BookingConfigRequest>({
    status: config?.status ?? 'active',
    calendar_mode: (config?.calendar_mode as 'cal_managed' | 'crm_google_insert') ?? 'cal_managed',
    default_event_type_id: config?.default_event_type_id ?? null,
    default_event_type_slug: config?.default_event_type_slug ?? '',
    default_username: config?.default_username ?? '',
    default_team_slug: config?.default_team_slug ?? '',
    organization_slug: config?.organization_slug ?? '',
    default_timezone: config?.default_timezone ?? 'America/Bogota',
    default_language: config?.default_language ?? 'es',
    default_length_minutes: config?.default_length_minutes ?? 30,
    cal_api_version: '2024-08-13',
  });

  const update = (key: keyof BookingConfigRequest, value: string | number | null) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const submit = async () => {
    setSaving(true);
    const payload = { ...form, status: 'active', cal_api_key: form.cal_api_key?.trim() || null };
    const result =
      mode === 'admin' && tenantId
        ? await configureAdminTenantCalComIntegration(accessToken, tenantId, payload)
        : await configureCalComIntegration(accessToken, payload);
    setSaving(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    onSaved(result.data);
  };

  return (
    <div className="grid gap-5 md:grid-cols-2">
      <label className="grid gap-1 text-sm md:col-span-2">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Cal.com API key <FieldHelp label="Cal.com API key" required={!config?.has_secret}>Créala en Cal.com → Settings → Developer → API Keys. Solo es obligatoria en la primera configuración.</FieldHelp></span>
        <input
          type="password"
          placeholder={config?.has_secret ? 'Conservar secreto actual' : 'cal_...'}
          className={FIELD_CLASS}
          onChange={(event) => update('cal_api_key', event.target.value)}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Event type ID <FieldHelp label="Event type ID" required>Abre el tipo de evento en Cal.com y copia su ID desde la URL o desde la respuesta de la API de event types.</FieldHelp></span>
        <input
          type="number"
          className={FIELD_CLASS}
          value={form.default_event_type_id ?? ''}
          onChange={(event) => update('default_event_type_id', event.target.value ? Number(event.target.value) : null)}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Event type slug <FieldHelp label="Event type slug" required={false}>Es la parte final de la URL pública del tipo de evento, por ejemplo demo-30-min.</FieldHelp></span>
        <input className={FIELD_CLASS} value={form.default_event_type_slug ?? ''} onChange={(event) => update('default_event_type_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Username <FieldHelp label="Username" required={false}>Es el nombre de usuario que aparece en tu URL pública de Cal.com.</FieldHelp></span>
        <input className={FIELD_CLASS} value={form.default_username ?? ''} onChange={(event) => update('default_username', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Team slug <FieldHelp label="Team slug" required={false}>Cópialo de la URL pública del equipo en Cal.com; déjalo vacío si el evento es personal.</FieldHelp></span>
        <input className={FIELD_CLASS} value={form.default_team_slug ?? ''} onChange={(event) => update('default_team_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Organization slug <FieldHelp label="Organization slug" required={false}>Cópialo de la URL o configuración de la organización; solo aplica a cuentas con organización.</FieldHelp></span>
        <input className={FIELD_CLASS} value={form.organization_slug ?? ''} onChange={(event) => update('organization_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Timezone <FieldHelp label="Timezone" required>Usa una zona IANA, por ejemplo America/Bogota, igual a la configurada en Cal.com.</FieldHelp></span>
        <input className={FIELD_CLASS} value={form.default_timezone ?? ''} onChange={(event) => update('default_timezone', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Calendar mode <FieldHelp label="Calendar mode" required>Selecciona cal_managed para que Cal.com gestione la agenda. crm_google_insert aún no crea eventos automáticamente.</FieldHelp></span>
        <select className={FIELD_CLASS} value={form.calendar_mode} onChange={(event) => update('calendar_mode', event.target.value)}>
          <option value="cal_managed">cal_managed</option>
          <option value="crm_google_insert">crm_google_insert</option>
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="flex items-center gap-1 font-medium text-muted-foreground">Duración <FieldHelp label="Duración" required>Indica en minutos la misma duración configurada en el tipo de evento de Cal.com.</FieldHelp></span>
        <input type="number" className={FIELD_CLASS} value={form.default_length_minutes ?? 30} onChange={(event) => update('default_length_minutes', Number(event.target.value || 30))} />
      </label>
      <div className="flex justify-end border-t border-border pt-4 md:col-span-2">
        <Button type="button" onClick={submit} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar Cal.com'}
        </Button>
      </div>
    </div>
  );
}
