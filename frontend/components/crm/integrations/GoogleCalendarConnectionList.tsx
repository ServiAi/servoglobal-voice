'use client';

import { useState, useEffect, useCallback } from 'react';
import { Calendar, PowerOff, RefreshCw, Trash2 } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { Button } from '@/components/ui/button';
import { fetchGoogleCalendars, syncGoogleCalendarConnection, updateGoogleCalendar } from '@/lib/api/crm';
import type { GoogleCalendarConnectionResponse, TenantGoogleCalendarResponse } from '@/types/crm';

type Props = {
  accessToken?: string;
  connections: GoogleCalendarConnectionResponse[];
  onDisconnect?: (connectionId: string) => Promise<void>;
  onDelete?: (connectionId: string) => Promise<void>;
};

export function GoogleCalendarConnectionList({ accessToken, connections, onDisconnect, onDelete }: Props) {
  const [disconnectingId, setDisconnectingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);
  const [calendarsByConnection, setCalendarsByConnection] = useState<Record<string, TenantGoogleCalendarResponse[]>>({});
  const [loadingCalendars, setLoadingCalendars] = useState<Record<string, boolean>>({});
  const [savingCalId, setSavingCalId] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const loadCalendars = useCallback(async (connectionId: string) => {
    if (!accessToken) return;
    setLoadingCalendars((prev) => ({ ...prev, [connectionId]: true }));
    try {
      const res = await fetchGoogleCalendars(accessToken, connectionId);
      if (res.ok) {
        setCalendarsByConnection((prev) => ({ ...prev, [connectionId]: res.data }));
      }
    } finally {
      setLoadingCalendars((prev) => ({ ...prev, [connectionId]: false }));
    }
  }, [accessToken]);

  useEffect(() => {
    if (!accessToken) return;
    connections.forEach((c) => {
      if (c.status === 'active' || c.status === 'connected') {
        loadCalendars(c.id);
      }
    });
  }, [accessToken, connections, loadCalendars]);

  const syncCalendars = async (connectionId: string) => {
    if (!accessToken) return;
    setSyncingId(connectionId);
    setFeedback(null);
    try {
      const res = await syncGoogleCalendarConnection(accessToken, connectionId);
      if (res.ok) {
        setCalendarsByConnection((prev) => ({ ...prev, [connectionId]: res.data.calendars }));
        setFeedback(`Se sincronizaron ${res.data.synced_count} calendarios correctamente.`);
      } else {
        setFeedback(res.detail || 'Error al sincronizar calendarios.');
      }
    } finally {
      setSyncingId(null);
    }
  };

  const toggleCalendarFlag = async (
    cal: TenantGoogleCalendarResponse,
    field: 'is_blocking' | 'is_booking_destination',
    currentVal: boolean
  ) => {
    if (!accessToken) return;
    setSavingCalId(`${cal.id}-${field}`);
    try {
      const payload = { [field]: !currentVal };
      const res = await updateGoogleCalendar(accessToken, cal.id, payload);
      if (res.ok) {
        setCalendarsByConnection((prev) => {
          const list = prev[cal.connection_id] || [];
          return {
            ...prev,
            [cal.connection_id]: list.map((item) => (item.id === cal.id ? res.data : item)),
          };
        });
      }
    } finally {
      setSavingCalId(null);
    }
  };

  const disconnect = async (connectionId: string) => {
    if (!onDisconnect) return;
    setDisconnectingId(connectionId);
    try {
      await onDisconnect(connectionId);
    } finally {
      setDisconnectingId(null);
    }
  };

  const handleDelete = async (connectionId: string, email?: string | null) => {
    if (!onDelete) return;
    const desc = email ? `de "${email}"` : '';
    if (!window.confirm(`¿Estás seguro de que deseas eliminar esta conexión ${desc}? Podrás volver a conectar la cuenta cuando lo desees.`)) {
      return;
    }
    setDeletingId(connectionId);
    try {
      await onDelete(connectionId);
    } finally {
      setDeletingId(null);
    }
  };

  if (connections.length === 0) {
    return <p className="rounded-lg border border-dashed border-border bg-muted/20 p-6 text-center text-sm text-muted-foreground">Sin conexiones Google Calendar.</p>;
  }

  return (
    <div className="grid gap-4">
      {feedback && (
        <div className="rounded-md border border-primary/20 bg-primary/10 p-3 text-xs text-primary">
          {feedback}
        </div>
      )}
      {connections.map((connection) => {
        const calendars = calendarsByConnection[connection.id] || [];
        const isSyncing = syncingId === connection.id;
        const isLoadingCal = loadingCalendars[connection.id];

        return (
          <div key={connection.id} className="rounded-lg border border-border bg-background p-4 text-sm transition-colors hover:border-primary/25">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="font-medium text-foreground">{connection.google_account_email ?? 'Cuenta Google'}</div>
                <div className="mt-1 truncate text-muted-foreground">{connection.calendar_summary ?? connection.calendar_id}</div>
                <div className={`mt-2 inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs font-semibold ${connection.status === 'active' || connection.status === 'connected' ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'border-border bg-muted text-muted-foreground'}`}>
                  <span aria-hidden="true" className="size-1.5 rounded-full bg-current" />
                  {connection.status === 'active' || connection.status === 'connected' ? 'Activa' : 'Desconectada'}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {accessToken && (connection.status === 'active' || connection.status === 'connected') && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => syncCalendars(connection.id)}
                    disabled={isSyncing}
                    aria-label="Sincronizar calendarios"
                  >
                    {isSyncing ? (
                      <CircularLoader size="xs" glow={false} />
                    ) : (
                      <RefreshCw className="h-4 w-4" />
                    )}
                    <span className="ml-1.5 hidden sm:inline">Sincronizar</span>
                  </Button>
                )}
                {onDisconnect && connection.status !== 'disconnected' && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => disconnect(connection.id)}
                    disabled={disconnectingId === connection.id || deletingId === connection.id}
                    aria-label="Desconectar Google Calendar"
                    title="Desconectar cuenta"
                  >
                    {disconnectingId === connection.id ? (
                      <CircularLoader size="xs" glow={false} />
                    ) : (
                      <PowerOff className="h-4 w-4" />
                    )}
                  </Button>
                )}
                {onDelete && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => handleDelete(connection.id, connection.google_account_email)}
                    disabled={deletingId === connection.id || disconnectingId === connection.id}
                    aria-label="Eliminar conexión Google Calendar"
                    title="Eliminar conexión"
                    className="text-destructive hover:bg-destructive/10 hover:text-destructive border-destructive/20"
                  >
                    {deletingId === connection.id ? (
                      <CircularLoader size="xs" glow={false} />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                    <span className="ml-1.5 hidden sm:inline">Eliminar</span>
                  </Button>
                )}
              </div>
            </div>

            {/* Calendars sub-list */}
            {(connection.status === 'active' || connection.status === 'connected') && (
              <div className="mt-4 border-t border-border pt-3">
                <div className="flex items-center justify-between text-xs font-medium text-muted-foreground mb-2">
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3.5 w-3.5" /> Calendarios disponibles ({calendars.length})
                  </span>
                  {isLoadingCal && <CircularLoader size="xs" glow={false} />}
                </div>

                {calendars.length === 0 && !isLoadingCal ? (
                  <p className="text-xs text-muted-foreground italic">No hay calendarios sincronizados. Haz clic en &quot;Sincronizar&quot; para consultar.</p>
                ) : (
                  <div className="space-y-2">
                    {calendars.map((cal) => (
                      <div key={cal.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 rounded-md bg-muted/30 p-2.5 text-xs">
                        <div className="min-w-0">
                          <div className="font-medium text-foreground flex items-center gap-1.5">
                            {cal.summary}
                            {cal.is_primary && (
                              <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">Principal</span>
                            )}
                          </div>
                          <div className="truncate text-muted-foreground text-[11px]">{cal.google_calendar_id}</div>
                        </div>
                        <div className="flex items-center gap-3 self-end sm:self-auto">
                          <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
                            <input
                              type="checkbox"
                              checked={cal.is_blocking}
                              disabled={savingCalId === `${cal.id}-is_blocking`}
                              onChange={() => toggleCalendarFlag(cal, 'is_blocking', cal.is_blocking)}
                              className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
                            />
                            <span>Bloquear</span>
                          </label>
                          <label className="flex items-center gap-1.5 cursor-pointer text-muted-foreground hover:text-foreground">
                            <input
                              type="checkbox"
                              checked={cal.is_booking_destination}
                              disabled={savingCalId === `${cal.id}-is_booking_destination`}
                              onChange={() => toggleCalendarFlag(cal, 'is_booking_destination', cal.is_booking_destination)}
                              className="rounded border-border text-primary focus:ring-primary h-3.5 w-3.5"
                            />
                            <span>Destino</span>
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
