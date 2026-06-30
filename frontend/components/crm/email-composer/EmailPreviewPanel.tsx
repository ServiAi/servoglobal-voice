'use client';

type PreviewState = {
  subject: string;
  html: string;
  text: string;
} | null;

export function EmailPreviewPanel({ preview, mode }: { preview: PreviewState; mode: 'html' | 'text' }) {
  if (mode === 'text') {
    return (
      <pre className="min-h-[420px] whitespace-pre-wrap rounded-md border border-border bg-muted/30 p-4 font-sans text-sm">
        {preview?.text ?? ''}
      </pre>
    );
  }
  return (
    <div
      className="min-h-[420px] rounded-md border border-border bg-background p-4 text-sm"
      dangerouslySetInnerHTML={{ __html: preview?.html ?? '' }}
    />
  );
}
