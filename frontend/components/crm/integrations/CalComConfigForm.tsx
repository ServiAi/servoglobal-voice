'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, SlidersHorizontal, Sparkles } from 'lucide-react';
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
  const [showAdvanced, setShowAdvanced] = useState(false);
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
    <div className="space-y-6">
      {/* Primary Connection Fields */}
      <div className="grid gap-5 md:grid-cols-2">
        <label className="grid gap-1 text-sm md:col-span-2">
          <span className="flex items-center gap-1 font-medium text-foreground">
            Cal.com API key (v2)
            <FieldHelp label="Cal.com API key" required={!config?.has_secret}>
              Genera tu API Key en Cal.com → Settings → Developer → API Keys. Solo es obligatoria en la primera configuración o al cambiarla.
            </FieldHelp>
          </span>
          <input
            type="password"
            placeholder={config?.has_secret ? 'Conservar secreto actual (••••••••)' : 'cal_live_...'}
            className={FIELD_CLASS}
            onChange={(event) => update('cal_api_key', event.target.value)}
          />
          <p className="text-xs text-muted-foreground mt-0.5">
            Conexión de primera clase con API v2. Permite sincronizar automáticamente tus tipos de evento, horarios y miembros de equipo.
          </p>
        </label>

        <label className="grid gap-1 text-sm">
          <span className="flex items-center gap-1 font-medium text-foreground">
            Zona Horaria Principal
            <FieldHelp label="Timezone" required>
              Zona horaria IANA de tu cuenta u organización, por ejemplo America/Bogota o America/Mexico_City.
            </FieldHelp>
          </span>
          <input
            className={FIELD_CLASS}
            value={form.default_timezone ?? ''}
            onChange={(event) => update('default_timezone', event.target.value)}
            placeholder="America/Bogota"
          />
        </label>

        <label className="grid gap-1 text-sm">
          <span className="flex items-center gap-1 font-medium text-foreground">
            Modo de Calendario
            <FieldHelp label="Calendar mode" required>
              Selecciona cal_managed para que Cal.com gestione de forma nativa la agenda, slots y reservas.
            </FieldHelp>
          </span>
          <select
            className={FIELD_CLASS}
            value={form.calendar_mode}
            onChange={(event) => update('calendar_mode', event.target.value)}
          >
            <option value="cal_managed">cal_managed (Recomendado - Cal.com gestiona agenda)</option>
            <option value="crm_google_insert">crm_google_insert (Inserción secundaria en Google)</option>
          </select>
        </label>
      </div>

      {/* Advanced / Legacy Configuration Accordion */}
      <div className="rounded-lg border border-border/80 bg-muted/10">
        <button
          type="button"
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex w-full items-center justify-between p-3.5 text-left text-sm font-medium text-muted-foreground transition hover:text-foreground"
        >
          <span className="flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-primary" />
            Configuración Avanzada y Campos Heredados (Opcional)
          </span>
          {showAdvanced ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>

        {showAdvanced && (
          <div className="border-t border-border/60 p-4 space-y-4">
            <p className="text-xs text-muted-foreground flex items-center gap-1.5 bg-primary/5 p-2 rounded border border-primary/20">
              <Sparkles className="h-3.5 w-3.5 text-primary shrink-0" />
              La nueva integración sincroniza tus tipos de evento automáticamente. Los siguientes parámetros se preservan para compatibilidad con integraciones manuales anteriores.
            </p>

            <div className="grid gap-4 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Event type ID heredado
                  <FieldHelp label="Event type ID" required={false}>
                    ID numérico de un tipo de evento específico si deseas forzarlo como fallback.
                  </FieldHelp>
                </span>
                <input
                  type="number"
                  className={FIELD_CLASS}
                  value={form.default_event_type_id ?? ''}
                  onChange={(event) => update('default_event_type_id', event.target.value ? Number(event.target.value) : null)}
                  placeholder="Ej: 123456"
                />
              </label>

              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Event type slug
                  <FieldHelp label="Event type slug" required={false}>
                    Slug del tipo de evento en la URL pública de Cal.com.
                  </FieldHelp>
                </span>
                <input
                  className={FIELD_CLASS}
                  value={form.default_event_type_slug ?? ''}
                  onChange={(event) => update('default_event_type_slug', event.target.value)}
                  placeholder="ej: demo-30-min"
                />
              </label>

              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Username
                  <FieldHelp label="Username" required={false}>
                    Usuario titular del calendario en Cal.com.
                  </FieldHelp>
                </span>
                <input
                  className={FIELD_CLASS}
                  value={form.default_username ?? ''}
                  onChange={(event) => update('default_username', event.target.value)}
                  placeholder="miusuario"
                />
              </label>

              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Team slug
                  <FieldHelp label="Team slug" required={false}>
                    Slug de equipo en Cal.com para eventos compartidos o round-robin nativo.
                  </FieldHelp>
                </span>
                <input
                  className={FIELD_CLASS}
                  value={form.default_team_slug ?? ''}
                  onChange={(event) => update('default_team_slug', event.target.value)}
                  placeholder="equipo-ventas"
                />
              </label>

              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Organization slug
                  <FieldHelp label="Organization slug" required={false}>
                    Slug de organización si tu cuenta pertenece a una org de Cal.com.
                  </FieldHelp>
                </span>
                <input
                  className={FIELD_CLASS}
                  value={form.organization_slug ?? ''}
                  onChange={(event) => update('organization_slug', event.target.value)}
                  placeholder="serviglobal"
                />
              </label>

              <label className="grid gap-1 text-sm">
                <span className="flex items-center gap-1 font-medium text-muted-foreground">
                  Duración por defecto (minutos)
                  <FieldHelp label="Duración" required={false}>
                    Duración estimada en minutos para citas manuales.
                  </FieldHelp>
                </span>
                <input
                  type="number"
                  className={FIELD_CLASS}
                  value={form.default_length_minutes ?? 30}
                  onChange={(event) => update('default_length_minutes', Number(event.target.value || 30))}
                />
              </label>
            </div>
          </div>
        )}
      </div>

      <div className="flex justify-end border-t border-border pt-4">
        <Button type="button" onClick={submit} disabled={saving}>
          {saving ? 'Guardando...' : 'Guardar Cal.com'}
        </Button>
      </div>
    </div>
  );
}
