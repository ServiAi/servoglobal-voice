'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Calendar, CalendarDays, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { disconnectGoogleCalendar, fetchGoogleCalendarConnectUrl } from '@/lib/api/crm';
import type { GoogleCalendarConnectionResponse } from '@/types/crm';
import { GoogleCalendarConnectionList } from './GoogleCalendarConnectionList';
import { FieldHelp } from './FieldHelp';

type Props = {
  accessToken?: string;
  connections: GoogleCalendarConnectionResponse[];
};

export function GoogleCalendarIntegrationCard({ accessToken, connections }: Props) {
  const [items, setItems] = useState(connections);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const connect = async () => {
    if (!accessToken) return;
    setLoading(true);
    setMessage(null);
    const result = await fetchGoogleCalendarConnectUrl(accessToken);
    setLoading(false);
    if (!result.ok) {
      setMessage(result.detail);
      return;
    }
    window.location.assign(result.data.url);
  };

  const disconnect = async (connectionId: string) => {
    if (!accessToken) return;
    const result = await disconnectGoogleCalendar(accessToken, connectionId);
    if (!result.ok) {
      setMessage(result.detail);
      return;
    }
    setItems((current) => current.map((item) => (item.id === connectionId ? result.data : item)));
  };

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="google-calendar-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-sky-500/10 text-sky-500">
            <CalendarDays className="h-5 w-5" />
          </span>
          <div>
            <h2 id="google-calendar-integration-title" className="text-lg font-semibold text-foreground">Google Calendar</h2>
            <p className="text-sm text-muted-foreground">Foundation OAuth, sin events.insert por defecto</p>
          </div>
        </div>
        {accessToken && (
          <div className="flex items-center gap-2">
            <Link href="/agenda">
              <Button type="button" variant="secondary">
                <Calendar className="mr-2 h-4 w-4" />
                Configurar agenda
              </Button>
            </Link>
            <Button type="button" variant="outline" onClick={connect} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <CalendarDays className="mr-2 h-4 w-4" />}
              Conectar cuenta
            </Button>
            <FieldHelp align="right" label="Conectar Google Calendar" required={false}>No requiere copiar credenciales. Haz clic en Conectar, elige tu cuenta de Google y autoriza el acceso solicitado.</FieldHelp>
          </div>
        )}
      </div>
      <div className="p-5">
        <GoogleCalendarConnectionList accessToken={accessToken} connections={items} onDisconnect={accessToken ? disconnect : undefined} />
      </div>
      {message && (
        <div role="alert" className="mx-5 mb-5 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
          {message}
        </div>
      )}
    </section>
  );
}
