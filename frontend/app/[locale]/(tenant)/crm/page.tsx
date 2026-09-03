import Link from 'next/link';
import { redirect } from 'next/navigation';
import { ArrowRight, CalendarDays, CheckSquare2, Layers3, Target } from 'lucide-react';
import { getAccessToken } from '@/lib/auth/server';
import { fetchCrmDashboard } from '@/lib/api/crm';
import { CrmMetricCard } from '@/components/crm/CrmMetricCard';

type Props = {
  params: Promise<{ locale: string }>;
};

export const dynamic = 'force-dynamic';

export default async function CrmHomePage({ params }: Props) {
  const { locale } = await params;
  const accessToken = await getAccessToken();
  if (!accessToken) {
    redirect(`/api/auth/login?returnTo=/${locale}/crm`);
  }

  const dashboardRes = await fetchCrmDashboard(accessToken);

  return (
    <div className="mx-auto flex w-full max-w-[1400px] flex-col gap-6">
      <header className="flex flex-col gap-3 border-b border-border pb-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">CRM</h1>
          <p className="mt-1 text-sm text-muted-foreground">Resumen comercial: leads, tareas y próximas acciones.</p>
        </div>
        <Link
          href={`/${locale}/crm/analytics`}
          className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
        >
          Ver rendimiento
          <ArrowRight aria-hidden="true" className="size-4" />
        </Link>
      </header>

      {dashboardRes.ok ? (
        <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Resumen comercial">
          <CrmMetricCard
            title="Leads del período"
            value={dashboardRes.data.kpis.total_leads}
            icon={Layers3}
            subtext={`${dashboardRes.data.kpis.new_leads} nuevos`}
          />
          <CrmMetricCard
            title="Leads abiertos"
            value={dashboardRes.data.kpis.open_leads}
            icon={Target}
            subtext={`${dashboardRes.data.kpis.follow_up_leads} en seguimiento`}
          />
          <CrmMetricCard
            title="Próxima acción"
            value={dashboardRes.data.kpis.leads_with_next_action}
            icon={CalendarDays}
            tone="positive"
            subtext="Leads con acción definida"
          />
          <CrmMetricCard
            title="Tareas pendientes"
            value={dashboardRes.data.kpis.pending_tasks}
            icon={CheckSquare2}
            tone={dashboardRes.data.kpis.overdue_tasks ? 'critical' : 'warning'}
            subtext={`${dashboardRes.data.kpis.overdue_tasks} vencidas`}
          />
        </section>
      ) : (
        <div className="rounded-xl border border-destructive/20 bg-destructive/10 p-4 text-destructive">
          Error cargando el resumen comercial: {dashboardRes.detail}
        </div>
      )}
    </div>
  );
}
