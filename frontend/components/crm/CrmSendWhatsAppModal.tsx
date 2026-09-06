'use client';

import { useEffect, useMemo, useState } from 'react';
import { RefreshCw, Send } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { fetchLeadMessages, fetchWhatsAppTemplates, previewLeadWhatsApp, sendLeadWhatsApp } from '@/lib/api/crm';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { LeadMessagesList } from '@/components/crm/messages/LeadMessagesList';
import type { WhatsAppMessageResponse, WhatsAppTemplateResponse } from '@/types/crm';

type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  contactName?: string | null;
  contactPhone?: string | null;
  onSent?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

export function CrmSendWhatsAppModal({
  open,
  onOpenChange,
  accessToken,
  leadId,
  contactName,
  contactPhone,
  onSent,
  onError,
  onSuccess,
}: Props) {
  const [templates, setTemplates] = useState<WhatsAppTemplateResponse[]>([]);
  const [messages, setMessages] = useState<WhatsAppMessageResponse[]>([]);
  const [templateKey, setTemplateKey] = useState('lead_follow_up');
  const [message, setMessage] = useState('');
  const [preview, setPreview] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_key === templateKey),
    [templateKey, templates]
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    Promise.all([fetchWhatsAppTemplates(accessToken), fetchLeadMessages(accessToken, leadId)]).then(([templateResult, messageResult]) => {
      if (cancelled) return;
      if (templateResult.ok) {
        setTemplates(templateResult.data);
        setTemplateKey(templateResult.data[0]?.template_key ?? 'lead_follow_up');
      } else {
        onError(templateResult.detail);
      }
      if (messageResult.ok) {
        setMessages(messageResult.data);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken, leadId, onError, open]);

  const runPreview = async () => {
    if (!contactPhone) {
      onError('El lead no tiene telefono para WhatsApp.');
      return;
    }
    setLoading(true);
    const result = await previewLeadWhatsApp(accessToken, leadId, {
      template_key: templateKey,
      message: message || null,
    });
    setLoading(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    setPreview(result.data.preview?.message ?? null);
  };

  const runSend = async () => {
    if (!contactPhone) {
      onError('El lead no tiene telefono para WhatsApp.');
      return;
    }
    setLoading(true);
    const result = await sendLeadWhatsApp(accessToken, leadId, {
      template_key: templateKey,
      message: message || null,
    });
    setLoading(false);
    if (!result.ok) {
      onError(result.detail);
      return;
    }
    onSuccess('WhatsApp enviado correctamente.');
    onSent?.();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Enviar WhatsApp</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="rounded-md border border-border bg-muted/20 p-3 text-sm">
            <div className="font-semibold text-foreground">{contactName || 'Lead sin nombre'}</div>
            <div className={contactPhone ? 'text-muted-foreground' : 'text-red-500'}>{contactPhone || 'Sin telefono'}</div>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Plantilla</span>
            <select className="rounded-md border border-border bg-background px-3 py-2" value={templateKey} onChange={(e) => setTemplateKey(e.target.value)}>
              {templates.map((template) => (
                <option key={template.id} value={template.template_key}>{template.name}</option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Mensaje</span>
            <textarea
              rows={4}
              className="rounded-md border border-border bg-background px-3 py-2"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder={selectedTemplate?.body ?? ''}
            />
          </label>
          {preview && (
            <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 p-3 text-sm text-foreground">
              {preview}
            </div>
          )}
          <LeadMessagesList messages={messages} />
        </div>
        <DialogFooter className="gap-2 sm:justify-end">
          <Button type="button" variant="outline" disabled={loading} onClick={runPreview} className="gap-2">
            {loading ? <CircularLoader size="xs" glow={false} /> : <RefreshCw className="h-4 w-4" />}
            Previsualizar
          </Button>
          <Button type="button" disabled={loading || !contactPhone} onClick={runSend} className="gap-2">
            {loading ? <CircularLoader size="xs" glow={false} /> : <Send className="h-4 w-4" />}
            Enviar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
