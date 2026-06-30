'use client';

import { FormEvent, useEffect, useMemo, useState } from 'react';
import { Eye, FileUp, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  createLeadFormToken,
  fetchCrmLeadDetail,
  fetchEmailAssets,
  fetchResendTemplates,
  fetchTenantForms,
  previewLeadEmail,
  sendLeadEmail,
  testResendIntegration,
  uploadEmailAsset,
} from '@/lib/api/crm';
import type { EmailAssetItem, EmailTemplateItem, TenantFormItem } from '@/types/crm';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  onSent?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

type PreviewState = {
  subject: string;
  html: string;
  text: string;
} | null;

const DEFAULT_CONTENT = `# Propuesta ServiGlobal IA

Hola {{contact_name}},

Gracias por tu interes en **ServiGlobal IA**.

{{signature:ServiGlobal IA}}`;

export function CrmSendEmailModal({
  open,
  onOpenChange,
  accessToken,
  leadId,
  onSent,
  onError,
  onSuccess,
}: Props) {
  const [templates, setTemplates] = useState<EmailTemplateItem[]>([]);
  const [assets, setAssets] = useState<EmailAssetItem[]>([]);
  const [forms, setForms] = useState<TenantFormItem[]>([]);
  const [toEmail, setToEmail] = useState('');
  const [templateKey, setTemplateKey] = useState('lead_proposal');
  const [subject, setSubject] = useState('Propuesta comercial ServiGlobal IA');
  const [content, setContent] = useState(DEFAULT_CONTENT);
  const [selectedAssets, setSelectedAssets] = useState<string[]>([]);
  const [selectedFormId, setSelectedFormId] = useState('');
  const [formTokenIds, setFormTokenIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<PreviewState>(null);
  const [tab, setTab] = useState<'editor' | 'html' | 'text'>('editor');
  const [loading, setLoading] = useState<'boot' | 'preview' | 'send' | 'test' | 'upload' | 'form' | null>(null);

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    setLoading('boot');
    Promise.all([
      fetchResendTemplates(accessToken),
      fetchEmailAssets(accessToken),
      fetchTenantForms(accessToken),
      fetchCrmLeadDetail(accessToken, leadId),
    ]).then(([templateResult, assetResult, formResult, leadResult]) => {
      if (!mounted) return;
      setLoading(null);
      if (templateResult.ok) setTemplates(templateResult.data);
      if (assetResult.ok) setAssets(assetResult.data);
      if (formResult.ok) {
        setForms(formResult.data);
        setSelectedFormId(formResult.data[0]?.id ?? '');
      }
      if (leadResult.ok) setToEmail(leadResult.data.contact.email ?? '');
      const failed = [templateResult, assetResult, formResult, leadResult].find((result) => !result.ok);
      if (failed && !failed.ok) onError(failed.detail);
    });
    return () => {
      mounted = false;
    };
  }, [accessToken, leadId, onError, open]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_key === templateKey),
    [templateKey, templates]
  );

  useEffect(() => {
    if (selectedTemplate) setSubject(selectedTemplate.subject);
  }, [selectedTemplate]);

  const payload = (previewOnly: boolean) => ({
    template_key: templateKey,
    subject,
    content_format: 'mdx',
    content,
    asset_ids: selectedAssets,
    form_token_ids: formTokenIds,
    preview_only: previewOnly,
  });

  const submit = async (previewOnly: boolean) => {
    setLoading(previewOnly ? 'preview' : 'send');
    const result = previewOnly
      ? await previewLeadEmail(accessToken, leadId, payload(true))
      : await sendLeadEmail(accessToken, leadId, payload(false));
    setLoading(null);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    if (previewOnly && result.data.preview) {
      setPreview(result.data.preview);
      setTab('html');
      return;
    }
    onSuccess('Email enviado correctamente.');
    onOpenChange(false);
    onSent?.();
  };

  const sendTest = async () => {
    if (!toEmail) return;
    setLoading('test');
    const result = await testResendIntegration(accessToken, { to_email: toEmail });
    setLoading(null);
    if (result.ok) {
      onSuccess('Correo de prueba enviado correctamente.');
    } else {
      onError(result.detail);
    }
  };

  const uploadAsset = async (event: FormEvent<HTMLInputElement>) => {
    const file = event.currentTarget.files?.[0];
    if (!file) return;
    setLoading('upload');
    const result = await uploadEmailAsset(accessToken, file);
    setLoading(null);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setAssets((current) => [result.data, ...current]);
    setSelectedAssets((current) => [...current, result.data.id]);
  };

  const insertFormLink = async () => {
    if (!selectedFormId) return;
    setLoading('form');
    const result = await createLeadFormToken(accessToken, selectedFormId, leadId);
    setLoading(null);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setFormTokenIds((current) => [...current, result.data.id]);
    setContent((current) => `${current}\n\n<Button href="${result.data.form_link}">Completar formulario</Button>`);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>Email Composer</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div className="grid gap-3">
            <label className="grid gap-1 text-sm">
              <span className="font-medium text-muted-foreground">Para</span>
              <input className="rounded-md border border-border bg-background px-3 py-2" value={toEmail} readOnly />
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-muted-foreground">Template</span>
                <select className="rounded-md border border-border bg-background px-3 py-2" value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
                  {templates.length === 0 && <option value="lead_proposal">lead_proposal</option>}
                  {templates.map((template) => (
                    <option key={template.id} value={template.template_key}>{template.name}</option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-muted-foreground">Asunto</span>
                <input className="rounded-md border border-border bg-background px-3 py-2" value={subject} onChange={(e) => setSubject(e.target.value)} />
              </label>
            </div>
            <div className="flex gap-2">
              {(['editor', 'html', 'text'] as const).map((item) => (
                <Button key={item} type="button" size="sm" variant={tab === item ? 'default' : 'outline'} onClick={() => setTab(item)}>
                  {item === 'editor' ? 'Editor' : item === 'html' ? 'Preview HTML' : 'Texto plano'}
                </Button>
              ))}
            </div>
            {tab === 'editor' && (
              <textarea rows={16} className="min-h-[360px] rounded-md border border-border bg-background px-3 py-2 font-mono text-sm" value={content} onChange={(e) => setContent(e.target.value)} />
            )}
            {tab === 'html' && (
              <div className="min-h-[360px] rounded-md border border-border bg-background p-4 text-sm" dangerouslySetInnerHTML={{ __html: preview?.html ?? '' }} />
            )}
            {tab === 'text' && (
              <pre className="min-h-[360px] whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-4 font-sans text-sm">{preview?.text ?? ''}</pre>
            )}
          </div>
          <aside className="grid content-start gap-4">
            <section className="grid gap-2">
              <div className="text-sm font-semibold text-foreground">Adjuntos</div>
              <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-md border border-border px-3 py-2 text-sm">
                <FileUp className="h-4 w-4" />
                Cargar
                <input type="file" className="sr-only" onChange={uploadAsset} />
              </label>
              <div className="grid max-h-48 gap-2 overflow-auto">
                {assets.map((asset) => (
                  <label key={asset.id} className="flex items-center gap-2 rounded-md border border-border px-2 py-2 text-sm">
                    <input
                      type="checkbox"
                      checked={selectedAssets.includes(asset.id)}
                      onChange={(e) => setSelectedAssets((current) => e.target.checked ? [...current, asset.id] : current.filter((id) => id !== asset.id))}
                    />
                    <span className="min-w-0 truncate">{asset.original_filename}</span>
                  </label>
                ))}
              </div>
            </section>
            <section className="grid gap-2">
              <div className="text-sm font-semibold text-foreground">Formulario</div>
              <select className="rounded-md border border-border bg-background px-3 py-2 text-sm" value={selectedFormId} onChange={(e) => setSelectedFormId(e.target.value)}>
                {forms.map((form) => <option key={form.id} value={form.id}>{form.name}</option>)}
              </select>
              <Button type="button" variant="outline" disabled={!selectedFormId || loading !== null} onClick={insertFormLink}>
                Insertar boton
              </Button>
            </section>
          </aside>
        </div>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" disabled={loading !== null} onClick={() => submit(true)} className="gap-2">
            {loading === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Preview
          </Button>
          <Button type="button" variant="outline" disabled={loading !== null || !toEmail} onClick={sendTest} className="gap-2">
            {loading === 'test' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Enviar prueba
          </Button>
          <Button type="button" disabled={loading !== null || loading === 'boot'} onClick={() => submit(false)} className="gap-2">
            {loading === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Enviar al lead
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
