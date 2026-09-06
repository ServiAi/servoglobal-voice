'use client';

import { AlertCircle } from 'lucide-react';
import { CircularLoader } from '@/components/ui/circular-loader';
import { cn } from '@/lib/utils';

type PreviewState = {
  subject: string;
  html: string;
  text: string;
} | null;

export function EmailPreviewPanel({
  preview,
  mode,
  loading = false,
  error = null,
}: {
  preview: PreviewState;
  mode: 'html' | 'text';
  loading?: boolean;
  error?: string | null;
}) {
  if (loading) {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-md border border-border bg-muted/30 p-4 text-muted-foreground">
        <CircularLoader size="lg" glow={true} label="Generando preview..." showLabel={true} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-md border border-destructive/20 bg-destructive/5 p-4">
        <AlertCircle className="h-6 w-6 text-destructive" />
        <p className="text-sm text-destructive">{error}</p>
      </div>
    );
  }

  if (!preview) {
    return (
      <div className="flex min-h-[420px] flex-col items-center justify-center gap-3 rounded-md border border-border bg-muted/30 p-4 text-muted-foreground">
        <p className="text-sm">Presiona Preview para generar HTML y texto plano.</p>
      </div>
    );
  }

  if (mode === 'text') {
    return (
      <pre className={cn('min-h-[420px] whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-4 font-sans text-sm')}>
        {preview.text}
      </pre>
    );
  }

  return (
    <div
      className="min-h-[420px] rounded-md border border-border bg-background p-4 text-sm"
      dangerouslySetInnerHTML={{ __html: preview.html }}
    />
  );
}