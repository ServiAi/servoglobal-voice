'use client';

import { Bot } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';

type AgentBuilderFeatureToggleProps = {
  enabled: boolean;
  saving: boolean;
  onToggle: (enabled: boolean) => void;
};

export function AgentBuilderFeatureToggle({
  enabled,
  saving,
  onToggle,
}: AgentBuilderFeatureToggleProps) {
  return (
    <section className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-700 dark:bg-zinc-900">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-cyan-500/10 text-cyan-600 dark:text-cyan-400">
            <Bot className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-lg font-medium text-zinc-900 dark:text-zinc-100">
              Agent Builder
            </h2>
            <p className="mt-1 max-w-md text-sm text-zinc-500 dark:text-zinc-400">
              Habilita la sección &quot;Agentes&quot; en <code className="rounded bg-zinc-100 px-1 py-0.5 dark:bg-zinc-800">/voice-ai/agents</code> para
              este tenant: crear, editar, publicar y versionar agentes propios.
            </p>
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Agent Builder"
          disabled={saving}
          onClick={() => onToggle(!enabled)}
          className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition disabled:cursor-not-allowed disabled:opacity-60 ${
            enabled ? 'bg-cyan-600 dark:bg-cyan-500' : 'bg-zinc-300 dark:bg-zinc-700'
          }`}
        >
          <span
            className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition ${
              enabled ? 'translate-x-6' : 'translate-x-1'
            }`}
          />
        </button>
      </div>
      <p className="mt-3 flex items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
        {saving ? (
          <>
            <CircularLoader size="xs" glow={false} />
            Guardando…
          </>
        ) : (
          <>
            Estado actual:{' '}
            <span
              className={
                enabled
                  ? 'font-medium text-cyan-600 dark:text-cyan-400'
                  : 'font-medium text-zinc-600 dark:text-zinc-300'
              }
            >
              {enabled ? 'Habilitado' : 'Deshabilitado'}
            </span>
          </>
        )}
      </p>
    </section>
  );
}
