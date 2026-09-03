import { PhoneCall } from 'lucide-react';
import type { CrmDashboardResponse } from '@/types/crm';
import { formatDuration } from '@/components/crm/lead-workspace/crm-format';

type Props = { data: CrmDashboardResponse; locale: string };

export function CallsPanel({ data, locale }: Props) {
  const calls = data.calls;
  const copy = locale === 'en'
    ? { title: 'Call performance (Ultravox)', subtitle: 'Results, duration, and usage reported by the provider.', total: 'Total', answered: 'Answered', unanswered: 'Unanswered', failed: 'Failed', voicemail: 'Voicemail', billed: 'Billed minutes', duration: 'Average duration', empty: 'No calls were recorded in this period.' }
    : { title: 'Rendimiento de llamadas (Ultravox)', subtitle: 'Resultados, duración y consumo reportados por el proveedor.', total: 'Total', answered: 'Atendidas', unanswered: 'No atendidas', failed: 'Fallidas', voicemail: 'Buzón de voz', billed: 'Minutos facturados', duration: 'Duración promedio', empty: 'No hay llamadas registradas en este período.' };

  return (
    <section className="rounded-xl border border-border bg-card p-4 sm:p-6" aria-labelledby="call-performance-title">
      <h2 id="call-performance-title" className="flex items-center gap-2 text-base font-semibold">
        <PhoneCall className="size-4 text-primary" />
        {copy.title}
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">{copy.subtitle}</p>
      {calls.total_calls ? (
        <>
          <dl className="mt-4 grid grid-cols-2 gap-4">
            <Metric label={copy.total} value={calls.total_calls} />
            <Metric label={copy.answered} value={calls.answered_calls} />
            <Metric label={copy.unanswered} value={calls.unanswered_calls} />
            <Metric label={copy.failed} value={calls.failed_calls} />
            <Metric label={copy.voicemail} value={calls.voicemail_calls} />
            <Metric label={copy.billed} value={`${calls.total_billed_minutes.toFixed(1)} min`} />
          </dl>
          <p className="mt-4 border-t border-border pt-4 text-sm text-muted-foreground">
            {copy.duration}: <strong className="text-foreground">{formatDuration(calls.average_duration_seconds)}</strong>
          </p>
        </>
      ) : (
        <Empty text={copy.empty} />
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-lg font-semibold">{value}</dd>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="mt-4 rounded-lg border border-dashed border-border p-6 text-center text-sm text-muted-foreground">{text}</div>;
}
