'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Eye, FileUp, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  createCallSummaryAsset,
  createLeadFormToken,
  fetchCallSummary,
  fetchCrmLeadDetail,
  fetchEmailAssets,
  fetchResendTemplates,
  fetchTenantForms,
  previewLeadEmail,
  recordCallSummaryInserted,
  sendLeadEmail,
  testResendIntegration,
  uploadEmailAsset,
} from '@/lib/api/crm';
import type { CallSummaryResponse, EmailAssetItem, EmailTemplateItem, TenantFormItem } from '@/types/crm';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { CallSummaryAttachmentButton } from './CallSummaryAttachmentButton';
import { CallSummaryInserter } from './CallSummaryInserter';
import { EmailMdxEditor } from './EmailMdxEditor';
import { EmailPreviewPanel } from './EmailPreviewPanel';
import { EmailSnippetsPanel } from './EmailSnippetsPanel';
import { EmailVariablesPanel } from './EmailVariablesPanel';

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

type LoadingState = 'boot' | 'preview' | 'send' | 'test' | 'upload' | 'form' | 'summary-md' | 'summary-txt' | null;

const DEFAULT_CONTENT = `# Propuesta ServiGlobal IA

Hola {{contact_name}},

Gracias por tu interes en **ServiGlobal IA**.

<Signature name="ServiGlobal IA" />`;

export function EmailComposerModal({
  open,
  onOpenChange,
  accessToken,
  leadId,
  onSent,
  onError,
  onSuccess,
}: Props) {
  const editorRef = useRef<HTMLTextAreaElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [templates, setTemplates] = useState<EmailTemplateItem[]>([]);
  const [assets, setAssets] = useState<EmailAssetItem[]>([]);
  const [forms, setForms] = useState<TenantFormItem[]>([]);
  const [callSummary, setCallSummary] = useState<CallSummaryResponse | null>(null);
  const [toEmail, setToEmail] = useState('');
  const [templateKey, setTemplateKey] = useState('lead_proposal');
  const [subject, setSubject] = useState('Propuesta comercial ServiGlobal IA');
  const [content, setContent] = useState(DEFAULT_CONTENT);
  const [selectedAssets, setSelectedAssets] = useState<string[]>([]);
  const [selectedFormId, setSelectedFormId] = useState('');
  const [formTokenIds, setFormTokenIds] = useState<string[]>([]);
  const [preview, setPreview] = useState<PreviewState>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewDirty, setPreviewDirty] = useState(true);
  const [tab, setTab] = useState<'editor' | 'html' | 'text'>('editor');
  const [loading, setLoading] = useState<LoadingState>(null);

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    setLoading('boot');
    Promise.all([
      fetchResendTemplates(accessToken),
      fetchEmailAssets(accessToken),
      fetchTenantForms(accessToken),
      fetchCrmLeadDetail(accessToken, leadId),
      fetchCallSummary(accessToken, leadId),
    ]).then(([templateResult, assetResult, formResult, leadResult, summaryResult]) => {
      if (!mounted) return;
      setLoading(null);
      if (templateResult.ok) setTemplates(templateResult.data);
      if (assetResult.ok) setAssets(assetResult.data);
      if (formResult.ok) {
        setForms(formResult.data);
        setSelectedFormId(formResult.data[0]?.id ?? '');
      }
      if (leadResult.ok) setToEmail(leadResult.data.contact.email ?? '');
      if (summaryResult.ok) setCallSummary(summaryResult.data);
      const failed = [templateResult, assetResult, formResult, leadResult, summaryResult].find((result) => !result.ok);
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

  useEffect(() => {
    setPreviewDirty(true);
  }, [subject, content, templateKey, selectedAssets, formTokenIds]);

  const payload = useCallback(
    (previewOnly: boolean) => ({
      template_key: templateKey,
      subject,
      content_format: 'mdx' as const,
      content,
      asset_ids: selectedAssets,
      form_token_ids: formTokenIds,
      preview_only: previewOnly,
    }),
    [templateKey, subject, content, selectedAssets, formTokenIds]
  );

  const doPreview = useCallback(async () => {
    if (loading === 'boot') return;
    if (!content.trim()) {
      setPreview(null);
      setPreviewError(null);
      setPreviewDirty(false);
      return;
    }
    setLoading('preview');
    setPreviewError(null);
    const result = await previewLeadEmail(accessToken, leadId, payload(true));
    setLoading(null);
    if (!result.ok) {
      setPreviewError(result.detail);
      setPreviewDirty(true);
      return;
    }
    if (result.data.preview) {
      setPreview(result.data.preview);
      setPreviewError(null);
      setPreviewDirty(false);
    }
  }, [accessToken, leadId, loading, content, payload]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!previewDirty || loading === 'boot') return;
    debounceRef.current = setTimeout(doPreview, 600);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [previewDirty, doPreview, loading]);

  const submit = async (previewOnly: boolean) => {
    if (previewDirty) {
      setLoading('preview');
      setPreviewError(null);
      const result = await previewLeadEmail(accessToken, leadId, payload(true));
      if (!result.ok) {
        setPreviewError(result.detail);
        setLoading(null);
        return;
      }
      if (result.data.preview) {
        setPreview(result.data.preview);
        setPreviewError(null);
        setPreviewDirty(false);
      }
      setLoading(null);
      if (previewOnly) {
        setTab('html');
        return;
      }
    }
    if (previewOnly && !previewDirty) {
      setTab('html');
      return;
    }
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

  const insertAtCursor = useCallback((snippet: string) => {
    const editor = editorRef.current;
    setContent((current) => {
      if (!editor) return `${current}\n\n${snippet}`;
      const start = editor.selectionStart;
      const end = editor.selectionEnd;
      const next = `${current.slice(0, start)}${snippet}${current.slice(end)}`;
      const cursor = start + snippet.length;
      queueMicrotask(() => {
        editor.focus();
        editor.setSelectionRange(cursor, cursor);
      });
      return next;
    });
  }, []);

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
    setAssets((current) => [result.data, ...current.filter((asset) => asset.id !== result.data.id)]);
    setSelectedAssets((current) => (current.includes(result.data.id) ? current : [...current, result.data.id]));
    event.currentTarget.value = '';
  };

  const uploadPastedImages = async (files: File[]) => {
    if (files.length === 0) return;
    setLoading('upload');
    const uploaded: EmailAssetItem[] = [];
    for (const file of files) {
      const result = await uploadEmailAsset(accessToken, file);
      if (!result.ok) {
        setLoading(null);
        onError(result.detail);
        return;
      }
      uploaded.push(result.data);
    }
    setLoading(null);
    setAssets((current) => [...uploaded, ...current.filter((asset) => !uploaded.some((item) => item.id === asset.id))]);
    setSelectedAssets((current) => {
      const currentIds = new Set(current);
      return [...current, ...uploaded.map((asset) => asset.id).filter((id) => !currentIds.has(id))];
    });
    insertAtCursor(uploaded.map((asset) => `[Imagen adjunta: ${asset.original_filename}]`).join('\n\n'));
    onSuccess(files.length === 1 ? 'Imagen pegada como adjunto.' : `${files.length} imagenes pegadas como adjuntos.`);
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
    insertAtCursor(`<Button href="${result.data.form_link}">Completar formulario</Button>`);
  };

  const insertCallSummary = async (variant: 'full' | 'short') => {
    const variable = variant === 'short' ? '{{call_summary_short}}' : '{{call_summary}}';
    insertAtCursor(`## Resumen de la llamada\n\n${variable}\n`);
    await recordCallSummaryInserted(accessToken, leadId, { variant });
  };

  const attachCallSummary = async (format: 'md' | 'txt') => {
    setLoading(format === 'md' ? 'summary-md' : 'summary-txt');
    const result = await createCallSummaryAsset(accessToken, leadId, { format });
    setLoading(null);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    const item: EmailAssetItem = {
      id: result.data.asset_id,
      original_filename: result.data.filename,
      mime_type: result.data.mime_type,
      file_size_bytes: result.data.file_size_bytes,
      status: 'uploaded',
    };
    setAssets((current) => [item, ...current]);
    setSelectedAssets((current) => [...current, item.id]);
    onSuccess(`Resumen adjuntado como .${format}.`);
  };

  const callSummaryAvailable = callSummary?.status === 'available';
  const summaryLoadingFormat = loading === 'summary-md' ? 'md' : loading === 'summary-txt' ? 'txt' : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-6xl">
        <DialogHeader>
          <DialogTitle>Email Composer Pro</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="grid gap-3">
            <label className="grid gap-1 text-sm">
              <span className="font-medium text-muted-foreground">Para</span>
              <input className="rounded-md border border-border bg-background px-3 py-2" value={toEmail} readOnly />
            </label>
            <div className="grid gap-3 md:grid-cols-2">
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-muted-foreground">Template</span>
                <select
                  className="rounded-md border border-border bg-background px-3 py-2"
                  value={templateKey}
                  onChange={(event) => setTemplateKey(event.target.value)}
                >
                  {templates.length === 0 && <option value="lead_proposal">lead_proposal</option>}
                  {templates.map((template) => (
                    <option key={template.id} value={template.template_key}>
                      {template.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="grid gap-1 text-sm">
                <span className="font-medium text-muted-foreground">Asunto</span>
                <input
                  className="rounded-md border border-border bg-background px-3 py-2"
                  value={subject}
                  onChange={(event) => setSubject(event.target.value)}
                />
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
              <EmailMdxEditor
                value={content}
                onChange={setContent}
                onInsert={insertAtCursor}
                onPasteImages={uploadPastedImages}
                textareaRef={editorRef}
              />
            )}
            {tab !== 'editor' && (
              <EmailPreviewPanel
                preview={preview}
                mode={tab}
                loading={loading === 'preview'}
                error={previewError}
              />
            )}
          </div>
          <aside className="grid content-start gap-4">
            <CallSummaryInserter summary={callSummary} disabled={loading !== null || !callSummaryAvailable} onInsert={insertCallSummary} />
            <CallSummaryAttachmentButton
              available={Boolean(callSummaryAvailable)}
              disabled={loading !== null}
              loadingFormat={summaryLoadingFormat}
              onAttach={attachCallSummary}
            />
            <EmailVariablesPanel onInsert={insertAtCursor} />
            <EmailSnippetsPanel
              onInsert={insertAtCursor}
              onInsertForm={insertFormLink}
              formDisabled={!selectedFormId || loading !== null}
            />
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
                      onChange={(event) =>
                        setSelectedAssets((current) =>
                          event.target.checked ? [...current, asset.id] : current.filter((id) => id !== asset.id)
                        )
                      }
                    />
                    <span className="min-w-0 truncate">{asset.original_filename}</span>
                    {selectedAssets.includes(asset.id) && (
                      <button
                        type="button"
                        className="ml-auto rounded-md px-2 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                        title="Desadjuntar"
                        aria-label={`Desadjuntar ${asset.original_filename}`}
                        onClick={(event) => {
                          event.preventDefault();
                          setSelectedAssets((current) => current.filter((id) => id !== asset.id));
                        }}
                      >
                        x
                      </button>
                    )}
                  </label>
                ))}
              </div>
            </section>
            <section className="grid gap-2">
              <div className="text-sm font-semibold text-foreground">Formulario</div>
              <select
                className="rounded-md border border-border bg-background px-3 py-2 text-sm"
                value={selectedFormId}
                onChange={(event) => setSelectedFormId(event.target.value)}
              >
                {forms.map((form) => (
                  <option key={form.id} value={form.id}>
                    {form.name}
                  </option>
                ))}
              </select>
              <p className="text-2xs text-muted-foreground">
                Para formularios, usa el boton &quot;Insertar boton&quot; de esta seccion. El boton CTA de la barra de herramientas es para enlaces genericos.
              </p>
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
          <Button
            type="button"
            disabled={loading !== null || loading === 'boot' || previewError !== null}
            onClick={() => submit(false)}
            className="gap-2"
          >
            {loading === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Enviar al lead
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
