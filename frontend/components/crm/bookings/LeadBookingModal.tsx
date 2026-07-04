'use client';

import { useEffect, useMemo, useState } from 'react';
import { CalendarCheck, Loader2, RefreshCw } from 'lucide-react';
import {
  createLeadBooking,
  cancelLeadBooking,
  fetchBookingConfig,
  fetchCalComSlots,
  fetchCrmLeadDetail,
  fetchLeadBookings,
  rescheduleLeadBooking,
} from '@/lib/api/crm';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import type { BookingConfigResponse, BookingResponse, LeadDetailResponse } from '@/types/crm';


type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessToken: string;
  leadId: string;
  onBooked?: () => void;
  onError: (message: string) => void;
  onSuccess: (message: string) => void;
};

type SlotItem = { start: string };

const tomorrow = () => {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  return date.toISOString().slice(0, 10);
};

function formatDateTime(value: string, timezone: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: timezone || 'America/Bogota',
  }).format(date);
}

export function LeadBookingModal({
  open,
  onOpenChange,
  accessToken,
  leadId,
  onBooked,
  onError,
  onSuccess,
}: Props) {
  const [lead, setLead] = useState<LeadDetailResponse | null>(null);
  const [config, setConfig] = useState<BookingConfigResponse | null>(null);
  const [bookings, setBookings] = useState<BookingResponse[]>([]);
  const [slots, setSlots] = useState<SlotItem[]>([]);
  const [date, setDate] = useState(tomorrow);
  const [jornada, setJornada] = useState('dia');
  const [selectedStart, setSelectedStart] = useState('');
  const [attendeeName, setAttendeeName] = useState('');
  const [attendeeEmail, setAttendeeEmail] = useState('');
  const [attendeePhone, setAttendeePhone] = useState('');
  const [notes, setNotes] = useState('');
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [creating, setCreating] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleCancel = async (bookingId: string) => {
    if (!confirm('¿Estás seguro de que deseas cancelar esta reunión?')) return;
    setActionLoading(bookingId);
    const result = await cancelLeadBooking(accessToken, leadId, bookingId);
    setActionLoading(null);
    if (result.ok) {
      setBookings((prev) => prev.filter((b) => b.id !== bookingId));
      onSuccess('Reunión cancelada correctamente.');
    } else {
      onError(result.detail);
    }
  };

  const handleReschedule = async (booking: BookingResponse) => {
    // Simplification: for now just reschedule to tomorrow at same time as placeholder
    // In a real app, this would open a date picker
    const tomorrowDate = new Date();
    tomorrowDate.setDate(tomorrowDate.getDate() + 1);
    const newStart = tomorrowDate.toISOString();
    const newEnd = new Date(tomorrowDate.getTime() + 3600000).toISOString();

    setActionLoading(booking.id);
    const result = await rescheduleLeadBooking(accessToken, leadId, booking.id, {
      new_start_time: newStart,
      new_end_time: newEnd,
    });
    setActionLoading(null);

    if (result.ok) {
      // Refresh bookings
      const refresh = await fetchLeadBookings(accessToken, leadId);
      if (refresh.ok) setBookings(refresh.data);
      onSuccess('Reunión reprogramada.');
    } else {
      onError(result.detail);
    }
  };

  const timezone = config?.default_timezone ?? 'America/Bogota';
  const canCreate = Boolean(selectedStart && attendeeName.trim() && attendeeEmail.trim());
  const selectedStartLabel = selectedStart ? formatDateTime(selectedStart, timezone) : '';
  const disabledReason = !selectedStart
    ? 'Selecciona un horario disponible para crear el booking.'
    : !attendeeName.trim()
      ? 'Confirma el nombre del asistente.'
      : !attendeeEmail.trim()
        ? 'Confirma el email del asistente.'
        : '';
  const sortedBookings = useMemo(
    () => [...bookings].sort((a, b) => Date.parse(b.start_at) - Date.parse(a.start_at)),
    [bookings]
  );

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setLocalError(null);
    Promise.all([
      fetchCrmLeadDetail(accessToken, leadId),
      fetchBookingConfig(accessToken),
      fetchLeadBookings(accessToken, leadId),
    ]).then(([leadResult, configResult, bookingsResult]) => {
      if (cancelled) return;
      if (!leadResult.ok) {
        setLocalError(leadResult.detail);
        return;
      }
      setLead(leadResult.data);
      setAttendeeName(leadResult.data.contact.name ?? '');
      setAttendeeEmail(leadResult.data.contact.email ?? '');
      setAttendeePhone(leadResult.data.contact.phone ?? '');
      if (configResult.ok) setConfig(configResult.data);
      if (bookingsResult.ok) setBookings(bookingsResult.data);
      if (!configResult.ok) setLocalError(configResult.detail);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [accessToken, leadId, open]);

  const loadSlots = async () => {
    setLoadingSlots(true);
    setLocalError(null);
    setSelectedStart('');
    const result = await fetchCalComSlots(accessToken, { date, jornada });
    setLoadingSlots(false);
    if (!result.ok) {
      setSlots([]);
      setLocalError(result.detail);
      return;
    }
    setSlots(result.data.available_slots ?? []);
  };

  const submit = async () => {
    if (!canCreate) {
      setLocalError('Selecciona un horario y confirma nombre/email del asistente.');
      return;
    }
    setCreating(true);
    setLocalError(null);
    const result = await createLeadBooking(accessToken, leadId, {
      start: selectedStart,
      timezone,
      attendee_name: attendeeName.trim(),
      attendee_email: attendeeEmail.trim(),
      attendee_phone: attendeePhone.trim() || null,
      notes: notes.trim() || null,
    });
    setCreating(false);
    if (!result.ok) {
      setLocalError(result.detail);
      onError(result.detail);
      return;
    }
    setBookings((current) => [result.data, ...current]);
    setSelectedStart('');
    onSuccess('Reunion agendada en Cal.com.');
    if (onBooked) onBooked();
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <CalendarCheck className="h-5 w-5 text-fuchsia-500" />
            Agendar reunion
          </DialogTitle>
          <DialogDescription>
            {lead?.contact.name ? `Lead: ${lead.contact.name}` : 'Selecciona un horario disponible'}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex min-h-40 items-center justify-center text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            Cargando agenda...
          </div>
        ) : (
          <div className="grid gap-5 lg:grid-cols-[1fr_260px]">
            <div className="space-y-4">
              {config?.status !== 'active' && (
                <div className="rounded-md border border-amber-500/20 bg-amber-500/10 p-3 text-sm text-amber-500">
                  Cal.com no esta activo para este tenant.
                </div>
              )}
              {localError && (
                <div className="rounded-md border border-red-500/20 bg-red-500/10 p-3 text-sm text-red-500">
                  {localError}
                </div>
              )}

              <div className="grid gap-3 sm:grid-cols-[1fr_150px_auto]">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Fecha</span>
                  <input
                    type="date"
                    value={date}
                    onChange={(event) => setDate(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Jornada</span>
                  <select
                    value={jornada}
                    onChange={(event) => setJornada(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  >
                    <option value="dia">Dia</option>
                    <option value="manana">Manana</option>
                    <option value="tarde">Tarde</option>
                  </select>
                </label>
                <div className="flex items-end">
                  <Button type="button" variant="outline" onClick={loadSlots} disabled={loadingSlots || config?.status !== 'active'}>
                    {loadingSlots ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
                    Buscar
                  </Button>
                </div>
              </div>

              <div className="grid min-h-24 grid-cols-1 gap-2 sm:grid-cols-2">
                {slots.map((slot) => (
                  <button
                    key={slot.start}
                    type="button"
                    onClick={() => setSelectedStart(slot.start)}
                    className={`rounded-md border px-3 py-2 text-left text-sm transition ${
                      selectedStart === slot.start
                        ? 'border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-500'
                        : 'border-border bg-background text-foreground hover:border-fuchsia-500/40'
                    }`}
                  >
                    {formatDateTime(slot.start, timezone)}
                  </button>
                ))}
                {!loadingSlots && slots.length === 0 && (
                  <div className="rounded-md border border-dashed border-border p-4 text-sm text-muted-foreground sm:col-span-2">
                    Busca horarios y selecciona una hora para activar Crear booking.
                  </div>
                )}
              </div>

              <div className="rounded-md border border-border bg-muted/30 p-3 text-sm" aria-live="polite">
                <div className="font-medium text-muted-foreground">Hora de agendamiento</div>
                <div className={selectedStartLabel ? 'mt-1 font-semibold text-foreground' : 'mt-1 text-muted-foreground'}>
                  {selectedStartLabel || 'Sin horario seleccionado.'}
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Nombre</span>
                  <input
                    value={attendeeName}
                    onChange={(event) => setAttendeeName(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Email</span>
                  <input
                    type="email"
                    value={attendeeEmail}
                    onChange={(event) => setAttendeeEmail(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Telefono</span>
                  <input
                    value={attendeePhone}
                    onChange={(event) => setAttendeePhone(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  />
                </label>
                <label className="grid gap-1 text-sm">
                  <span className="font-medium text-muted-foreground">Notas</span>
                  <input
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    className="h-10 rounded-md border border-border bg-background px-3"
                  />
                </label>
              </div>
            </div>

            <aside className="rounded-md border border-border p-3">
              <h3 className="mb-2 text-sm font-semibold text-foreground">Bookings</h3>
              <div className="space-y-2">
                <div className="space-y-2">
                  {sortedBookings.slice(0, 5).map((booking) => (
                    <div key={booking.id} className="group relative rounded-md bg-muted/40 p-2 text-xs">
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <div className="font-medium text-foreground">{formatDateTime(booking.start_at, booking.timezone)}</div>
                          <div className="text-muted-foreground capitalize">{booking.status}</div>
                        </div>
                        <div className="flex gap-1">
                          <button
                            type="button"
                            onClick={() => handleReschedule(booking)}
                            disabled={actionLoading === booking.id}
                            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-fuchsia-500 hover:bg-fuchsia-500/10 disabled:opacity-50"
                          >
                            Reprogramar
                          </button>
                          <button
                            type="button"
                            onClick={() => handleCancel(booking.id)}
                            disabled={actionLoading === booking.id}
                            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-500 hover:bg-red-500/10 disabled:opacity-50"
                          >
                            Cancelar
                          </button>
                        </div>
                      </div>
                      {actionLoading === booking.id && (
                        <div className="absolute inset-0 flex items-center justify-center bg-background/50 rounded-md">
                          <Loader2 className="h-3 w-3 animate-spin" />
                        </div>
                      )}
                    </div>
                  ))}
                  {sortedBookings.length === 0 && <p className="text-xs text-muted-foreground">Sin bookings previos.</p>}
                </div>
              </div>
            </aside>
          </div>
        )}

        <DialogFooter>
          {!canCreate && !loading && (
            <p className="mr-auto text-left text-xs text-muted-foreground">
              {disabledReason}
            </p>
          )}
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={creating}>
            Cerrar
          </Button>
          <Button type="button" onClick={submit} disabled={!canCreate || creating || loading}>
            {creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
            Crear booking
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
