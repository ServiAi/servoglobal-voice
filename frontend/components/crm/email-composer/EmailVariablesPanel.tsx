'use client';

import { Button } from '@/components/ui/button';

const VARIABLES = [
  'contact_name',
  'contact_email',
  'company',
  'interest',
  'industry',
  'use_case',
  'volume',
  'pain_point',
  'source',
  'campaign',
  'lead_id',
  'call_summary',
  'call_summary_short',
  'last_call_date',
  'form_link',
];

export function EmailVariablesPanel({ onInsert }: { onInsert: (snippet: string) => void }) {
  return (
    <section className="grid gap-2">
      <div className="text-sm font-semibold text-foreground">Variables</div>
      <div className="grid grid-cols-2 gap-2">
        {VARIABLES.map((name) => (
          <Button
            key={name}
            type="button"
            size="sm"
            variant="outline"
            title={`{{${name}}}`}
            onClick={() => onInsert(`{{${name}}}`)}
            className="justify-start truncate text-xs"
          >
            {name}
          </Button>
        ))}
      </div>
    </section>
  );
}
