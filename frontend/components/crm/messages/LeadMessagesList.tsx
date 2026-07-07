'use client';

import type { WhatsAppMessageResponse } from '@/types/crm';

type Props = {
  messages: WhatsAppMessageResponse[];
};

export function LeadMessagesList({ messages }: Props) {
  if (!messages.length) {
    return <div className="rounded-md border border-border bg-muted/20 p-3 text-xs text-muted-foreground">Sin mensajes registrados.</div>;
  }
  return (
    <div className="max-h-56 space-y-2 overflow-y-auto pr-1">
      {messages.map((message) => (
        <div key={message.id} className="rounded-md border border-border bg-background p-3 text-xs">
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="font-semibold text-foreground">{message.direction === 'inbound' ? 'Entrante' : 'Saliente'}</span>
            <span className="text-muted-foreground">{message.status}</span>
          </div>
          <p className="text-muted-foreground">{message.message_preview || message.template_key || 'Mensaje WhatsApp'}</p>
        </div>
      ))}
    </div>
  );
}
