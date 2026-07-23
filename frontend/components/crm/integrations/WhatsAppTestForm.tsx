'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Loader2, RefreshCw, Send, ShieldCheck } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  fetchAdminTenantWhatsAppTemplates,
  fetchWhatsAppTemplates,
  sendAdminTenantWhatsAppTestMessage,
  sendWhatsAppTestMessage,
  syncAdminTenantWhatsAppTemplates,
  syncWhatsAppTemplates,
  testAdminTenantWhatsAppIntegration,
  testWhatsAppIntegration,
} from '@/lib/api/crm';
import type { WhatsAppTemplateResponse, WhatsAppTemplateSyncResponse } from '@/types/crm';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken: string;
  templates: WhatsAppTemplateResponse[];
  disabled?: boolean;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  onSuccess: (message: string) => void;
  onError: (message: string) => void;
};

type TemplateParameter = { key: string; label?: string };

export function WhatsAppTestForm({ accessToken, templates: initialTemplates, disabled, mode = 'tenant', tenantId, onSuccess, onError }: Props) {
  const [templates, setTemplates] = useState(initialTemplates);
  const [toPhone, setToPhone] = useState('');
  const [templateKey, setTemplateKey] = useState(initialTemplates[0]?.template_key ?? '');
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<'connection' | 'sync' | 'message' | null>(null);
  const [syncResult, setSyncResult] = useState<WhatsAppTemplateSyncResponse | null>(null);
  const [messageResult, setMessageResult] = useState<string | null>(null);
  const approvedTemplates = templates.filter((template) => (
    template.status === 'active'
    && template.variables?.source === 'meta_sync'
    && template.variables?.meta_status === 'APPROVED'
  ));

  useEffect(() => {
    setTemplates(initialTemplates);
    const firstApproved = initialTemplates.find((template) => template.variables?.source === 'meta_sync' && template.variables?.meta_status === 'APPROVED');
    setTemplateKey((current) => current || firstApproved?.template_key || '');
  }, [initialTemplates]);

  const selectedTemplate = approvedTemplates.find((template) => template.template_key === templateKey);
  const parameters = useMemo<TemplateParameter[]>(() => {
    const value = selectedTemplate?.variables?.parameters;
    if (!Array.isArray(value)) return [];
    return value.filter((item): item is TemplateParameter => (
      typeof item === 'object' && item !== null && typeof (item as TemplateParameter).key === 'string'
    ));
  }, [selectedTemplate]);

  const validateConnection = async () => {
    setBusy('connection');
    const result = mode === 'admin' && tenantId
      ? await testAdminTenantWhatsAppIntegration(accessToken, tenantId)
      : await testWhatsAppIntegration(accessToken);
    setBusy(null);
    if (!result.ok) return onError(result.detail);
    onSuccess(result.data.message || 'Conexión exitosa con Meta. Esta prueba no envía mensajes.');
  };

  const syncTemplates = async () => {
    setBusy('sync');
    const result = mode === 'admin' && tenantId
      ? await syncAdminTenantWhatsAppTemplates(accessToken, tenantId)
      : await syncWhatsAppTemplates(accessToken);
    if (!result.ok) {
      setBusy(null);
      return onError(result.detail);
    }
    const refreshed = mode === 'admin' && tenantId
      ? await fetchAdminTenantWhatsAppTemplates(accessToken, tenantId)
      : await fetchWhatsAppTemplates(accessToken);
    setBusy(null);
    setSyncResult(result.data);
    if (refreshed.ok) {
      setTemplates(refreshed.data);
      const firstApproved = refreshed.data.find((template) => template.variables?.source === 'meta_sync' && template.variables?.meta_status === 'APPROVED');
      setTemplateKey(firstApproved?.template_key ?? '');
    }
    onSuccess('Plantillas aprobadas sincronizadas desde Meta.');
  };

  const sendTestMessage = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy('message');
    setMessageResult(null);
    const payload = { to_phone: toPhone, template_key: templateKey, variables };
    const result = mode === 'admin' && tenantId
      ? await sendAdminTenantWhatsAppTestMessage(accessToken, tenantId, payload)
      : await sendWhatsAppTestMessage(accessToken, payload);
    setBusy(null);
    if (!result.ok) return onError(result.detail);
    const detail = `Mensaje de prueba enviado. ID Meta: ${result.data.provider_message_id || 'pendiente'}. Estado inicial: ${result.data.status}. El estado final se actualizará por webhook.`;
    setMessageResult(detail);
    onSuccess('Mensaje de prueba enviado.');
  };

  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <div>
          <h3 className="font-medium text-foreground">Validar conexión</h3>
          <p className="text-sm text-muted-foreground">Esta prueba valida el token y el Phone Number ID. No envía mensajes.</p>
        </div>
        <Button type="button" disabled={disabled || busy !== null} variant="outline" className="gap-2" onClick={validateConnection}>
          {busy === 'connection' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
          Validar conexión con Meta
        </Button>
      </section>

      <section className="space-y-4 border-t border-border pt-5">
        <div>
          <h3 className="font-medium text-foreground">Plantillas y mensaje de prueba</h3>
          <p className="text-sm text-muted-foreground">Sincroniza únicamente plantillas aprobadas y usa una para enviar un WhatsApp real.</p>
        </div>
        <Button type="button" disabled={disabled || busy !== null} variant="outline" className="gap-2" onClick={syncTemplates}>
          {busy === 'sync' ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Sincronizar plantillas aprobadas
        </Button>
        {syncResult && (
          <div className="grid gap-2 rounded-md border border-border bg-muted/30 p-3 text-sm sm:grid-cols-2">
            <span>Plantillas consultadas: {syncResult.fetched_count}</span>
            <span>Aprobadas: {syncResult.approved_count}</span>
            <span>Sincronizadas: {syncResult.synced_count}</span>
            <span>Ignoradas: {syncResult.ignored_count}</span>
          </div>
        )}

        <form onSubmit={sendTestMessage} className="space-y-3">
          <div className="grid gap-3 md:grid-cols-2">
            <label className="space-y-1 text-sm">
              <span className="flex items-center gap-1">Plantilla aprobada <FieldHelp label="Plantilla aprobada" required>Primero sincroniza las plantillas que Meta muestra con estado APPROVED y selecciona una de la lista.</FieldHelp></span>
              <select className="w-full rounded-md border border-border bg-background px-3 py-2" value={templateKey} onChange={(event) => { setTemplateKey(event.target.value); setVariables({}); }} required>
                <option value="">Selecciona una plantilla</option>
                {approvedTemplates.map((template) => <option key={template.id} value={template.template_key}>{template.name} ({template.language})</option>)}
              </select>
            </label>
            <label className="space-y-1 text-sm">
              <span className="flex items-center gap-1">Número destino <FieldHelp label="Número destino" required>Escribe el número que recibirá la prueba en formato internacional, por ejemplo +573001112233.</FieldHelp></span>
              <input className="w-full rounded-md border border-border bg-background px-3 py-2" value={toPhone} onChange={(event) => setToPhone(event.target.value)} placeholder="+573001112233" minLength={8} maxLength={32} required />
            </label>
          </div>
          {parameters.length > 0 && (
            <div className="grid gap-3 md:grid-cols-2">
              {parameters.map((parameter) => (
                <label key={parameter.key} className="space-y-1 text-sm">
                  <span className="flex items-center gap-1">
                    {parameter.label || `Variable ${parameter.key}`}
                    <FieldHelp label={parameter.label || `Variable ${parameter.key}`} required>Escribe el valor que reemplazará esta variable de la plantilla aprobada en Meta.</FieldHelp>
                  </span>
                  <input className="w-full rounded-md border border-border bg-background px-3 py-2" value={variables[parameter.key] || ''} onChange={(event) => setVariables((current) => ({ ...current, [parameter.key]: event.target.value }))} required />
                </label>
              ))}
            </div>
          )}
          <Button type="submit" disabled={disabled || busy !== null || !templateKey} className="gap-2">
            {busy === 'message' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Enviar mensaje de prueba
          </Button>
          {messageResult && <p className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-emerald-500">{messageResult}</p>}
        </form>
      </section>
    </div>
  );
}
