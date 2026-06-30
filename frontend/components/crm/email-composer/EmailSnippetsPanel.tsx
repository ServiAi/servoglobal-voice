'use client';

import { Button } from '@/components/ui/button';

type Snippet = {
  label: string;
  value?: string;
  formCta?: boolean;
};

const SNIPPETS: Snippet[] = [
  {
    label: 'Propuesta breve',
    value: 'Hola {{contact_name}},\n\nTe comparto una propuesta basada en tu interes: **{{interest}}**.\n\n<Signature name="ServiGlobal IA" />',
  },
  {
    label: 'CTA formulario',
    formCta: true,
  },
  {
    label: 'Nota comercial',
    value: '<Callout type="info">\nPodemos adaptar esta solucion a tu operacion actual.\n</Callout>',
  },
];

export function EmailSnippetsPanel({
  onInsert,
  onInsertForm,
  formDisabled = false,
}: {
  onInsert: (snippet: string) => void;
  onInsertForm: () => void | Promise<void>;
  formDisabled?: boolean;
}) {
  return (
    <section className="grid gap-2">
      <div className="text-sm font-semibold text-foreground">Snippets</div>
      <div className="grid gap-2">
        {SNIPPETS.map((snippet) => {
          const isFormCta = Boolean(snippet.formCta);
          return (
            <Button
              key={snippet.label}
              type="button"
              size="sm"
              variant="outline"
              disabled={isFormCta && formDisabled}
              onClick={() => {
                if (isFormCta) {
                  void onInsertForm();
                  return;
                }
                onInsert(snippet.value ?? '');
              }}
              className="justify-start"
            >
              {snippet.label}
            </Button>
          );
        })}
      </div>
    </section>
  );
}
