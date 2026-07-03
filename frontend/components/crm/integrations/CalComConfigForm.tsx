'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import type { BookingConfigRequest, BookingConfigResponse } from '@/types/crm';
import { configureAdminTenantCalComIntegration, configureCalComIntegration } from '@/lib/api/crm';

type Props = {
  accessToken: string;
  config?: BookingConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSaved: (config: BookingConfigResponse) => void;
  onError: (message: string) => void;
};

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
    <div className="grid gap-3 md:grid-cols-2">
      <label className="grid gap-1 text-sm md:col-span-2">
        <span className="font-medium text-muted-foreground">Cal.com API key</span>
        <input
          type="password"
          placeholder={config?.has_secret ? 'Conservar secreto actual' : 'cal_...'}
          className="rounded-md border border-border bg-background px-3 py-2"
          onChange={(event) => update('cal_api_key', event.target.value)}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Event type ID</span>
        <input
          type="number"
          className="rounded-md border border-border bg-background px-3 py-2"
          value={form.default_event_type_id ?? ''}
          onChange={(event) => update('default_event_type_id', event.target.value ? Number(event.target.value) : null)}
        />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Event type slug</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={form.default_event_type_slug ?? ''} onChange={(event) => update('default_event_type_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Username</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={form.default_username ?? ''} onChange={(event) => update('default_username', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Team slug</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={form.default_team_slug ?? ''} onChange={(event) => update('default_team_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Organization slug</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={form.organization_slug ?? ''} onChange={(event) => update('organization_slug', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Timezone</span>
        <input className="rounded-md border border-border bg-background px-3 py-2" value={form.default_timezone ?? ''} onChange={(event) => update('default_timezone', event.target.value)} />
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Calendar mode</span>
        <select className="rounded-md border border-border bg-background px-3 py-2" value={form.calendar_mode} onChange={(event) => update('calendar_mode', event.target.value)}>
          <option value="cal_managed">cal_managed</option>
          <option value="crm_google_insert">crm_google_insert</option>
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-medium text-muted-foreground">Duracion</span>
        <input type="number" className="rounded-md border border-border bg-background px-3 py-2" value={form.default_length_minutes ?? 30} onChange={(event) => update('default_length_minutes', Number(event.target.value || 30))} />
      </label>
      <div className="md:col-span-2">
        <Button type="button" onClick={submit} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar Cal.com'}
        </Button>
      </div>
    </div>
  );
}
