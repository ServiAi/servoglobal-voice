'use client';

import { Button } from '@/components/ui/button';

const SNIPPETS = [
  {
    label: 'Propuesta breve',
    value: 'Hola {{contact_name}},\n\nTe comparto una propuesta basada en tu interes: **{{interest}}**.\n\n<Signature name="ServiGlobal IA" />',
  },
  {
    label: 'CTA formulario',
    value: '<Button href="{{form_link}}">Completar formulario</Button>',
  },
  {
    label: 'Nota comercial',
    value: '<Callout type="info">\nPodemos adaptar esta solucion a tu operacion actual.\n</Callout>',
  },
];

export function EmailSnippetsPanel({ onInsert }: { onInsert: (snippet: string) => void }) {
  return (
    <section className="grid gap-2">
      <div className="text-sm font-semibold text-foreground">Snippets</div>
      <div className="grid gap-2">
        {SNIPPETS.map((snippet) => (
          <Button
            key={snippet.label}
            type="button"
            size="sm"
            variant="outline"
            onClick={() => onInsert(snippet.value)}
            className="justify-start"
          >
            {snippet.label}
          </Button>
        ))}
      </div>
    </section>
  );
}
