'use client';

import { useState } from 'react';
import { Loader2, PowerOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { GoogleCalendarConnectionResponse } from '@/types/crm';

type Props = {
  connections: GoogleCalendarConnectionResponse[];
  onDisconnect?: (connectionId: string) => Promise<void>;
};

export function GoogleCalendarConnectionList({ connections, onDisconnect }: Props) {
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);

  const disconnect = async (connectionId: string) => {
    if (!onDisconnect) return;
    setDisconnectingId(connectionId);
    try {
      await onDisconnect(connectionId);
    } finally {
      setDisconnectingId(null);
    }
  };

  if (connections.length === 0) {
    return <p className="rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center text-sm text-muted-foreground">Sin conexiones Google Calendar.</p>;
  }
  return (
    <div className="grid gap-2">
      {connections.map((connection) => (
        <div key={connection.id} className="flex items-start justify-between gap-3 rounded-lg border border-border bg-background p-4 text-sm transition-colors hover:border-primary/25">
          <div className="min-w-0">
            <div className="font-medium text-foreground">{connection.google_account_email ?? 'Cuenta Google'}</div>
            <div className="mt-1 truncate text-muted-foreground">{connection.calendar_summary ?? connection.calendar_id}</div>
            <div className={`mt-2 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold ${connection.status === 'active' ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-border bg-muted text-muted-foreground'}`}>
              <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
              {connection.status === 'active' ? 'Activa' : 'Desconectada'}
            </div>
          </div>
          {onDisconnect && connection.status !== 'disconnected' && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => disconnect(connection.id)}
              disabled={disconnectingId === connection.id}
              aria-label="Desconectar Google Calendar"
            >
              {disconnectingId === connection.id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PowerOff className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
      ))}
    </div>
  );
}
