'use client';

import type { FormEvent } from 'react';
import { useState } from 'react';
import { Loader2, Pencil, Plus, RefreshCw, Send, Trash2, Eye, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  createAdminTenantWhatsAppTemplate,
  createWhatsAppTemplate,
  deleteAdminTenantWhatsAppTemplate,
  deleteWhatsAppTemplate,
  previewAdminTenantWhatsAppTemplate,
  previewWhatsAppTemplate,
  submitAdminTenantWhatsAppTemplate,
  submitWhatsAppTemplate,
  syncAdminTenantWhatsAppTemplateStatus,
  syncWhatsAppTemplateStatus,
  updateAdminTenantWhatsAppTemplate,
  updateWhatsAppTemplate,
} from '@/lib/api/whatsapp-templates';
import type {
  WhatsAppTemplateButtonItem,
  WhatsAppTemplateDetailResponse,
  WhatsAppTemplatePreviewResponse,
  WhatsAppTemplateResponse,
} from '@/types/crm';
import { FieldHelp } from '../FieldHelp';

type Props = {
  accessToken: string;
  templates: WhatsAppTemplateResponse[];
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  disabled?: boolean;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

type DraftForm = {
  template_key: string;
  name: string;
  category: string;
  language: string;
  header_text: string;
  body: string;
  footer_text: string;
  buttons: WhatsAppTemplateButtonItem[];
};

const FIELD_CLASS = 'min-h-10 rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15 disabled:cursor-not-allowed disabled:opacity-60';

const STATUS_LABEL: Record<string, string> = {
  draft: 'Borrador',
  pending: 'Pendiente de Meta',
  approved: 'Aprobada',
  rejected: 'Rechazada',
  disabled: 'Deshabilitada',
};

const STATUS_CLASS: Record<string, string> = {
  draft: 'border-border bg-muted text-muted-foreground',
  pending: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  approved: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  rejected: 'border-destructive/20 bg-destructive/10 text-destructive',
  disabled: 'border-border bg-muted text-muted-foreground',
};

const EMPTY_FORM: DraftForm = {
  template_key: '',
  name: '',
  category: 'utility',
  language: 'es',
  header_text: '',
  body: '',
  footer_text: '',
  buttons: [],
};

export function WhatsAppTemplateManager({ accessToken, templates: initialTemplates, mode = 'tenant', tenantId, disabled, onError, onSuccess }: Props) {
  const [templates, setTemplates] = useState(initialTemplates);
  const [form, setForm] = useState<DraftForm | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [previewFor, setPreviewFor] = useState<string | null>(null);
  const [previewData, setPreviewData] = useState<WhatsAppTemplatePreviewResponse | null>(null);

  const isAdmin = mode === 'admin' && !!tenantId;

  const refresh = (template: WhatsAppTemplateDetailResponse) => {
    setTemplates((current) => {
      const exists = current.some((item) => item.id === template.id);
      return exists
        ? current.map((item) => (item.id === template.id ? template : item))
        : [...current, template];
    });
  };

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...EMPTY_FORM });
  };

  const openEdit = (template: WhatsAppTemplateResponse) => {
    setEditingId(template.id);
    const detail = template as Partial<WhatsAppTemplateDetailResponse>;
    setForm({
      template_key: template.template_key,
      name: template.name,
      category: template.category,
      language: template.language,
      header_text: detail.header_text ?? '',
      body: template.body,
      footer_text: detail.footer_text ?? '',
      buttons: detail.buttons ?? [],
    });
  };

  const closeForm = () => {
    setForm(null);
    setEditingId(null);
  };

  const handleSubmitForm = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) return;
    setBusyId(editingId ?? 'new');
    const buttons = form.buttons.filter((button) => button.text.trim());

    if (editingId) {
      const payload = {
        name: form.name,
        header_text: form.header_text || null,
        body: form.body,
        footer_text: form.footer_text || null,
        buttons,
      };
      const result = isAdmin
        ? await updateAdminTenantWhatsAppTemplate(accessToken, tenantId!, editingId, payload)
        : await updateWhatsAppTemplate(accessToken, editingId, payload);
      setBusyId(null);
      if (!result.ok) return onError(result.detail);
      refresh(result.data);
      onSuccess('Plantilla actualizada.');
    } else {
      const payload = {
        template_key: form.template_key,
        name: form.name,
        category: form.category,
        language: form.language,
        header_text: form.header_text || null,
        body: form.body,
        footer_text: form.footer_text || null,
        buttons,
      };
      const result = isAdmin
        ? await createAdminTenantWhatsAppTemplate(accessToken, tenantId!, payload)
        : await createWhatsAppTemplate(accessToken, payload);
      setBusyId(null);
      if (!result.ok) return onError(result.detail);
      refresh(result.data);
      onSuccess('Borrador de plantilla creado.');
    }
    closeForm();
  };

  const handleDelete = async (template: WhatsAppTemplateResponse) => {
    setBusyId(template.id);
    const result = isAdmin
      ? await deleteAdminTenantWhatsAppTemplate(accessToken, tenantId!, template.id)
      : await deleteWhatsAppTemplate(accessToken, template.id);
    setBusyId(null);
    if (!result.ok) return onError(result.detail);
    if (template.status === 'draft') {
      setTemplates((current) => current.filter((item) => item.id !== template.id));
      onSuccess('Borrador eliminado.');
    } else {
      setTemplates((current) =>
        current.map((item) => (item.id === template.id ? { ...item, status: 'disabled' } : item))
      );
      onSuccess('Plantilla deshabilitada.');
    }
  };

  const handleSubmitToMeta = async (template: WhatsAppTemplateResponse) => {
    setBusyId(template.id);
    const result = isAdmin
      ? await submitAdminTenantWhatsAppTemplate(accessToken, tenantId!, template.id)
      : await submitWhatsAppTemplate(accessToken, template.id);
    setBusyId(null);
    if (!result.ok) return onError(result.detail);
    setTemplates((current) =>
      current.map((item) => (item.id === template.id ? { ...item, status: 'pending' } : item))
    );
    onSuccess('Plantilla enviada a Meta para revisión.');
  };

  const handleSyncStatus = async (template: WhatsAppTemplateResponse) => {
    setBusyId(template.id);
    const result = isAdmin
      ? await syncAdminTenantWhatsAppTemplateStatus(accessToken, tenantId!, template.id)
      : await syncWhatsAppTemplateStatus(accessToken, template.id);
    setBusyId(null);
    if (!result.ok) return onError(result.detail);
    onSuccess(`Estado sincronizado: ${result.data.meta_status ?? result.data.status}.`);
    if (result.data.status === 'success') {
      const nextStatus = result.data.meta_status === 'APPROVED' ? 'approved' : result.data.meta_status === 'REJECTED' ? 'rejected' : 'pending';
      setTemplates((current) =>
        current.map((item) => (item.id === template.id ? { ...item, status: nextStatus } : item))
      );
    }
  };

  const handlePreview = async (template: WhatsAppTemplateResponse) => {
    if (previewFor === template.id) {
      setPreviewFor(null);
      setPreviewData(null);
      return;
    }
    setBusyId(template.id);
    const result = isAdmin
      ? await previewAdminTenantWhatsAppTemplate(accessToken, tenantId!, template.id)
      : await previewWhatsAppTemplate(accessToken, template.id);
    setBusyId(null);
    if (!result.ok) return onError(result.detail);
    setPreviewFor(template.id);
    setPreviewData(result.data);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium text-foreground">Plantillas</h3>
          <p className="text-sm text-muted-foreground">Crea, edita y envía plantillas de WhatsApp a revisión de Meta.</p>
        </div>
        <Button type="button" variant="outline" size="sm" className="gap-2" disabled={disabled} onClick={openCreate}>
          <Plus className="h-4 w-4" /> Nueva plantilla
        </Button>
      </div>

      <ul className="space-y-2">
        {templates.map((template) => (
          <li key={template.id} className="rounded-md border border-border p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="truncate font-medium text-foreground">{template.name}</p>
                <p className="truncate text-xs text-muted-foreground">{template.template_key}</p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded-md border px-2 py-0.5 text-xs font-semibold ${STATUS_CLASS[template.status] ?? STATUS_CLASS.draft}`}>
                  {STATUS_LABEL[template.status] ?? template.status}
                </span>
                <Button type="button" variant="ghost" size="sm" disabled={busyId === template.id} onClick={() => handlePreview(template)} title="Previsualizar">
                  {busyId === template.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
                </Button>
                {(template.status === 'draft' || template.status === 'rejected') && (
                  <>
                    <Button type="button" variant="ghost" size="sm" onClick={() => openEdit(template)} title="Editar">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button type="button" variant="ghost" size="sm" disabled={disabled || busyId === template.id} onClick={() => handleSubmitToMeta(template)} title="Enviar a Meta">
                      <Send className="h-4 w-4" />
                    </Button>
                  </>
                )}
                {template.status === 'pending' && (
                  <Button type="button" variant="ghost" size="sm" disabled={disabled || busyId === template.id} onClick={() => handleSyncStatus(template)} title="Sincronizar estado">
                    <RefreshCw className="h-4 w-4" />
                  </Button>
                )}
                {template.status !== 'disabled' && (
                  <Button type="button" variant="ghost" size="sm" disabled={busyId === template.id} onClick={() => handleDelete(template)} title="Eliminar">
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
            {template.status === 'rejected' && (template as Partial<WhatsAppTemplateDetailResponse>).rejection_reason && (
              <p className="mt-2 rounded-md border border-destructive/20 bg-destructive/10 p-2 text-xs text-destructive">
                Meta rechazó esta plantilla: {(template as Partial<WhatsAppTemplateDetailResponse>).rejection_reason}
              </p>
            )}
            {previewFor === template.id && previewData && (
              <div className="mt-3 max-w-sm rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3 text-sm">
                {previewData.header_text && <p className="mb-1 font-semibold text-foreground">{previewData.header_text}</p>}
                <p className="whitespace-pre-wrap text-foreground">{previewData.body}</p>
                {previewData.footer_text && <p className="mt-1 text-xs text-muted-foreground">{previewData.footer_text}</p>}
              </div>
            )}
          </li>
        ))}
        {templates.length === 0 && (
          <li className="rounded-md border border-dashed border-border p-4 text-center text-sm text-muted-foreground">
            No hay plantillas todavía.
          </li>
        )}
      </ul>

      {form && (
        <form onSubmit={handleSubmitForm} className="space-y-4 rounded-md border border-border bg-muted/10 p-4">
          <div className="flex items-center justify-between">
            <h4 className="font-medium text-foreground">{editingId ? 'Editar plantilla' : 'Nueva plantilla'}</h4>
            <Button type="button" variant="ghost" size="sm" onClick={closeForm}><X className="h-4 w-4" /></Button>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Nombre técnico <FieldHelp label="Nombre técnico" required>Identificador único para esta plantilla, en minúsculas y guiones bajos. No se puede cambiar después de creada.</FieldHelp></span>
              <input required disabled={!!editingId} className={FIELD_CLASS} value={form.template_key} onChange={(e) => setForm({ ...form, template_key: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Nombre visible <FieldHelp label="Nombre visible" required>Nombre descriptivo para identificar la plantilla en el panel.</FieldHelp></span>
              <input required className={FIELD_CLASS} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Categoría <FieldHelp label="Categoría" required>Categoría de Meta: utility (transaccional), marketing o authentication.</FieldHelp></span>
              <select disabled={!!editingId} className={FIELD_CLASS} value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                <option value="utility">Utility</option>
                <option value="marketing">Marketing</option>
                <option value="authentication">Authentication</option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Idioma <FieldHelp label="Idioma" required>Código de idioma de Meta, por ejemplo es, es_CO o en_US.</FieldHelp></span>
              <input required disabled={!!editingId} className={FIELD_CLASS} value={form.language} onChange={(e) => setForm({ ...form, language: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm md:col-span-2">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Encabezado (opcional) <FieldHelp label="Encabezado" required={false}>{'Texto corto arriba del mensaje. Puede incluir variables como {{nombre}}.'}</FieldHelp></span>
              <input className={FIELD_CLASS} value={form.header_text} onChange={(e) => setForm({ ...form, header_text: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm md:col-span-2">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Cuerpo del mensaje <FieldHelp label="Cuerpo del mensaje" required>{'Texto principal. Usa {{nombre_variable}} para insertar variables, por ejemplo {{fecha_cita}}.'}</FieldHelp></span>
              <textarea required rows={4} className={FIELD_CLASS} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} />
            </label>
            <label className="flex flex-col gap-1 text-sm md:col-span-2">
              <span className="flex items-center gap-1 font-medium text-muted-foreground">Pie de página (opcional) <FieldHelp label="Pie de página" required={false}>Texto corto abajo del mensaje, hasta 60 caracteres. No admite variables.</FieldHelp></span>
              <input maxLength={60} className={FIELD_CLASS} value={form.footer_text} onChange={(e) => setForm({ ...form, footer_text: e.target.value })} />
            </label>
          </div>

          <div className="space-y-2">
            <span className="flex items-center gap-1 text-sm font-medium text-muted-foreground">
              Botones de respuesta rápida (opcional)
              <FieldHelp label="Botones" required={false}>Hasta 3 botones que el destinatario puede tocar para responder.</FieldHelp>
            </span>
            {form.buttons.map((button, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  className={`${FIELD_CLASS} flex-1`}
                  placeholder="Texto del botón"
                  maxLength={25}
                  value={button.text}
                  onChange={(e) => {
                    const buttons = [...form.buttons];
                    buttons[index] = { ...buttons[index], text: e.target.value };
                    setForm({ ...form, buttons });
                  }}
                />
                <Button type="button" variant="ghost" size="sm" onClick={() => setForm({ ...form, buttons: form.buttons.filter((_, i) => i !== index) })}>
                  <X className="h-4 w-4" />
                </Button>
              </div>
            ))}
            {form.buttons.length < 3 && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setForm({ ...form, buttons: [...form.buttons, { type: 'QUICK_REPLY', text: '' }] })}
              >
                <Plus className="h-4 w-4" /> Agregar botón
              </Button>
            )}
          </div>

          <div className="flex justify-end gap-2 border-t border-border pt-4">
            <Button type="button" variant="outline" onClick={closeForm}>Cancelar</Button>
            <Button type="submit" disabled={busyId === (editingId ?? 'new')} className="gap-2">
              {busyId === (editingId ?? 'new') && <Loader2 className="h-4 w-4 animate-spin" />}
              {editingId ? 'Guardar cambios' : 'Crear borrador'}
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
