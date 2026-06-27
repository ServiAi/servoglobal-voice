'use client';

import { useEffect, useMemo, useState } from 'react';
import { Eye, Loader2, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { fetchResendTemplates, leadActionEmail } from '@/lib/api/crm';
import type { EmailTemplateItem } from '@/types/crm';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  onSent?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

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
  const [templateKey, setTemplateKey] = useState('lead_proposal');
  const [subject, setSubject] = useState('Propuesta comercial ServiGlobal IA');
  const [message, setMessage] = useState('Hola, adjunto la propuesta conversada.');
  const [preview, setPreview] = useState<{ subject: string; text: string } | null>(null);
  const [loading, setLoading] = useState<'preview' | 'send' | 'templates' | null>(null);

  useEffect(() => {
    if (!open) return;
    let mounted = true;
    setLoading('templates');
    fetchResendTemplates(accessToken).then((result) => {
      if (!mounted) return;
      setLoading(null);
      if (!result.ok) {
        onError(result.detail);
        return;
      }
      setTemplates(result.data);
    });
    return () => {
      mounted = false;
    };
  }, [accessToken, onError, open]);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_key === templateKey),
    [templateKey, templates]
  );

  useEffect(() => {
    if (selectedTemplate && !subject) {
      setSubject(selectedTemplate.subject);
    }
  }, [selectedTemplate, subject]);

  const submit = async (previewOnly: boolean) => {
    setLoading(previewOnly ? 'preview' : 'send');
    setPreview(null);
    const result = await leadActionEmail(accessToken, leadId, {
      template_key: templateKey,
      subject,
      message,
      asset_ids: [],
      preview_only: previewOnly,
    });
    setLoading(null);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    if (previewOnly && result.data.preview) {
      setPreview({ subject: result.data.preview.subject, text: result.data.preview.text });
      return;
    }
    onSuccess('Email enviado correctamente.');
    onOpenChange(false);
    onSent?.();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Enviar email</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Template</span>
            <select className="rounded-md border border-border bg-background px-3 py-2" value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
              {templates.length === 0 && <option value="lead_proposal">lead_proposal</option>}
              {templates.map((template) => (
                <option key={template.id} value={template.template_key}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Subject</span>
            <input className="rounded-md border border-border bg-background px-3 py-2" value={subject} onChange={(e) => setSubject(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Message</span>
            <textarea rows={6} className="rounded-md border border-border bg-background px-3 py-2" value={message} onChange={(e) => setMessage(e.target.value)} />
          </label>
          {preview && (
            <div className="rounded-md border border-border bg-muted/30 p-3 text-sm">
              <div className="font-semibold text-foreground">{preview.subject}</div>
              <pre className="mt-2 whitespace-pre-wrap font-sans text-muted-foreground">{preview.text}</pre>
            </div>
          )}
        </div>
        <DialogFooter className="gap-2">
          <Button type="button" variant="outline" disabled={loading !== null} onClick={() => submit(true)} className="gap-2">
            {loading === 'preview' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Eye className="h-4 w-4" />}
            Preview
          </Button>
          <Button type="button" disabled={loading !== null || loading === 'templates'} onClick={() => submit(false)} className="gap-2">
            {loading === 'send' ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Enviar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
