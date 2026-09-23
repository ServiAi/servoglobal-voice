'use client';

import { FormEvent, useState } from 'react';
import { useTranslations } from 'next-intl';
import { FlaskConical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CircularLoader } from '@/components/ui/circular-loader';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { testCustomToolAction } from '@/app/[locale]/(tenant)/voice-ai/tools/actions';
import type { CustomToolResponse, CustomToolTestResponse } from '@/types/tools-custom';

type Props = {
  tool: CustomToolResponse;
  onClose: () => void;
};

const FIELD_CLASS =
  'min-h-24 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs shadow-xs outline-none transition focus:border-primary/60 focus:ring-2 focus:ring-primary/15';

export function CustomToolTestPanel({ tool, onClose }: Props) {
  const t = useTranslations('crm.tools.test');
  const [argumentsText, setArgumentsText] = useState('{}');
  const [busy, setBusy] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [result, setResult] = useState<CustomToolTestResponse | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);

  const run = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setJsonError(null);
    setRequestError(null);
    setResult(null);

    let parsedArguments: Record<string, unknown>;
    try {
      parsedArguments = JSON.parse(argumentsText || '{}');
    } catch {
      setJsonError(t('invalidJson'));
      return;
    }

    setBusy(true);
    const response = await testCustomToolAction(tool.id, { arguments: parsedArguments });
    setBusy(false);
    if (!response.ok) {
      setRequestError(response.detail);
      return;
    }
    setResult(response.data);
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-1rem)] w-[calc(100vw-1rem)] max-w-lg grid-rows-[auto_minmax(0,1fr)] gap-0 overflow-hidden p-0 sm:max-h-[calc(100dvh-2rem)] sm:w-full">
        <DialogHeader className="border-b border-border bg-muted/30 p-4 pr-12 sm:p-5 sm:pr-12">
          <div className="mb-2 flex size-10 items-center justify-center rounded-md border border-border bg-background text-muted-foreground">
            <FlaskConical className="size-5" aria-hidden="true" />
          </div>
          <DialogTitle>{t('title', { name: tool.name })}</DialogTitle>
          <DialogDescription>{t('subtitle')}</DialogDescription>
        </DialogHeader>
        <form onSubmit={run} className="grid min-h-0 grid-rows-[minmax(0,1fr)_auto]">
          <div className="min-h-0 space-y-4 overflow-y-auto overscroll-contain p-4 sm:p-5">
            {jsonError && (
              <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {jsonError}
              </p>
            )}
            {requestError && (
              <p role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
                {requestError}
              </p>
            )}

            <label className="space-y-1 text-sm">
              <span className="font-medium text-foreground">{t('arguments')}</span>
              <textarea
                className={FIELD_CLASS}
                value={argumentsText}
                onChange={(e) => setArgumentsText(e.target.value)}
                spellCheck={false}
              />
            </label>

            {result && (
              <div className="space-y-3 rounded-lg border border-border bg-muted/20 p-3">
                <div className="flex items-center justify-between text-sm">
                  <span
                    className={`inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-semibold ${
                      result.success
                        ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300'
                        : 'border-destructive/25 bg-destructive/10 text-destructive'
                    }`}
                  >
                    {result.success ? t('success') : t('failure')}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {result.status_code !== null && t('statusCode', { code: result.status_code })}
                    {result.latency_ms !== null && ` · ${t('latency', { ms: result.latency_ms })}`}
                  </span>
                </div>
                {result.error_code && <p className="text-xs text-destructive">{result.error_code}</p>}
                {result.mapped_result && (
                  <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-all rounded-md bg-background p-2 text-xs">
                    {JSON.stringify(result.mapped_result, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>

          <DialogFooter className="border-t border-border bg-background p-4 sm:px-5">
            <Button type="button" variant="outline" onClick={onClose}>
              {t('close')}
            </Button>
            <Button type="submit" disabled={busy} className="gap-2">
              {busy && <CircularLoader size="xs" glow={false} />}
              {t('run')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
