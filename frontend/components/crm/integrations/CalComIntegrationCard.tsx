'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  CalendarCheck,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  RefreshCw,
  Users,
} from 'lucide-react';
import Link from 'next/link';
import { CircularLoader } from '@/components/ui/circular-loader';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import type { BookingConfigResponse } from '@/types/crm';
import type { CalComDiscoveryResponse } from '@/types/scheduling';
import { fetchCalComDiscovery, syncCalComProvider } from '@/lib/api/scheduling';
import { CalComConfigForm } from './CalComConfigForm';
import { CalComTestForm } from './CalComTestForm';

type Props = {
  accessToken: string;
  initialConfig?: BookingConfigResponse;
  mode?: 'tenant' | 'admin';
  tenantId?: string;
  locale?: string;
};

export function CalComIntegrationCard({
  accessToken,
  initialConfig,
  mode = 'tenant',
  tenantId,
  locale = 'es',
}: Props) {
  const [config, setConfig] = useState(initialConfig);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [discovery, setDiscovery] = useState<CalComDiscoveryResponse | null>(null);
  const [loadingDiscovery, setLoadingDiscovery] = useState(false);
  const [syncing, setSyncing] = useState(false);

  const isActive = config?.status === 'active';
  const hasSecret = Boolean(config?.has_secret);

  const notify = (type: 'success' | 'error', text: string) => {
    setMessage({ type, text });
    setTimeout(() => setMessage(null), 5000);
  };

  const loadDiscovery = useCallback(async () => {
    if (!hasSecret) return;
    setLoadingDiscovery(true);
    const res = await fetchCalComDiscovery(accessToken);
    setLoadingDiscovery(false);
    if (res.ok) {
      setDiscovery(res.data);
    }
  }, [accessToken, hasSecret]);

  useEffect(() => {
    if (isActive && hasSecret) {
      loadDiscovery();
    }
  }, [isActive, hasSecret, loadDiscovery]);


  const handleSync = async () => {
    setSyncing(true);
    const res = await syncCalComProvider(accessToken);
    setSyncing(false);
    if (res.ok) {
      const { event_types = 0, schedules = 0, teams = 0 } = res.data.counts;
      notify(
        'success',
        `Sincronización exitosa: ${event_types} tipos de cita, ${schedules} horarios y ${teams} equipos sincronizados.`
      );
      setDiscovery(res.data);
    } else {
      notify('error', `Error al sincronizar con Cal.com: ${res.detail}`);
    }
  };

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-xs" aria-labelledby="calcom-integration-title">
      <div className="flex flex-col gap-3 border-b border-border bg-muted/20 p-5 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-3">
          <span className="inline-flex h-10 w-10 items-center justify-center rounded-md bg-fuchsia-500/10 text-fuchsia-500">
            <CalendarCheck className="h-5 w-5" />
          </span>
          <div>
            <h2 id="calcom-integration-title" className="text-lg font-semibold text-foreground">Cal.com</h2>
            <p className="text-sm text-muted-foreground">Motor de scheduling de primera clase (API v2)</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-2 self-start rounded-md border px-3 py-1.5 text-xs font-semibold md:self-auto ${
              isActive
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                : 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300'
            }`}
          >
            {isActive ? <CheckCircle2 className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            {isActive ? `${config?.calendar_mode} · Activa` : config?.status ?? 'Sin configurar'}
          </span>
        </div>
      </div>

      {/* Discovery Summary Banner if connected */}
      {isActive && hasSecret && (
        <div className="border-b border-border bg-muted/10 p-5 space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Cuenta Cal.com Sincronizada
              </span>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-sm font-semibold text-foreground">
                  {discovery?.account?.name || discovery?.account?.username || 'Cuenta Cal.com'}
                </span>
                {discovery?.account?.email && (
                  <span className="text-xs text-muted-foreground">({discovery.account.email})</span>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleSync}
                disabled={syncing || loadingDiscovery}
                className="gap-1.5 text-xs"
              >
                {syncing ? (
                  <CircularLoader size="xs" glow={false} />
                ) : (
                  <RefreshCw className="h-3.5 w-3.5" />
                )}
                Sincronizar ahora
              </Button>

              <Link href={`/${locale}/agenda`}>
                <Button size="sm" className="gap-1.5 text-xs">
                  <ExternalLink className="h-3.5 w-3.5" />
                  Ir a Agenda
                </Button>
              </Link>
            </div>
          </div>

          {/* Counts overview */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
            <Card className="p-3 bg-background/50 border-border/60">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Layers className="h-3.5 w-3.5 text-primary" /> Tipos de Cita
              </div>
              <div className="text-xl font-bold text-foreground">
                {discovery?.counts?.event_types ?? 0}
              </div>
            </Card>

            <Card className="p-3 bg-background/50 border-border/60">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Clock className="h-3.5 w-3.5 text-primary" /> Horarios de Atención
              </div>
              <div className="text-xl font-bold text-foreground">
                {discovery?.counts?.schedules ?? 0}
              </div>
            </Card>

            <Card className="p-3 bg-background/50 border-border/60">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Users className="h-3.5 w-3.5 text-primary" /> Equipos
              </div>
              <div className="text-xl font-bold text-foreground">
                {discovery?.counts?.teams ?? 0}
              </div>
            </Card>

            <Card className="p-3 bg-background/50 border-border/60">
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
                <Users className="h-3.5 w-3.5 text-primary" /> Membresías
              </div>
              <div className="text-xl font-bold text-foreground">
                {discovery?.counts?.memberships ?? 0}
              </div>
            </Card>
          </div>
        </div>
      )}

      <div className="space-y-6 p-5">
        <CalComConfigForm
          accessToken={accessToken}
          config={config}
          mode={mode}
          tenantId={tenantId}
          onSaved={(nextConfig) => {
            setConfig(nextConfig);
            notify('success', 'Configuración Cal.com guardada.');
            loadDiscovery();
          }}
          onError={(text) => notify('error', text)}
        />
        <div className="flex justify-end border-t border-border pt-5">
          <CalComTestForm
            accessToken={accessToken}
            mode={mode}
            tenantId={tenantId}
            disabled={!isActive || !config?.has_secret}
            onSuccess={(text) => {
              notify('success', text);
              loadDiscovery();
            }}
            onError={(text) => notify('error', text)}
          />
        </div>
      </div>

      {message && (
        <div
          role="status"
          className={`mx-5 mb-5 rounded-md border p-3 text-sm ${
            message.type === 'success'
              ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
              : 'border-destructive/20 bg-destructive/10 text-destructive'
          }`}
        >
          {message.text}
        </div>
      )}
    </section>
  );
}
