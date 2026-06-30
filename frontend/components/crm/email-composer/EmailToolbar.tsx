'use client';

import type { ComponentType } from 'react';
import {
  Bold,
  Heading1,
  Heading2,
  Italic,
  Link,
  List,
  ListOrdered,
  MessageSquareQuote,
  Minus,
  MousePointerClick,
  PenLine,
  Quote,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

type Tool = {
  label: string;
  icon: ComponentType<{ className?: string }>;
  snippet: string;
};

const TOOLS: Tool[] = [
  { label: 'Titulo H1', icon: Heading1, snippet: '# Titulo\n\n' },
  { label: 'Subtitulo H2', icon: Heading2, snippet: '## Subtitulo\n\n' },
  { label: 'Negrita', icon: Bold, snippet: '**texto importante**' },
  { label: 'Cursiva', icon: Italic, snippet: '*texto destacado*' },
  { label: 'Lista', icon: List, snippet: '- Punto clave\n- Siguiente punto\n' },
  { label: 'Lista numerada', icon: ListOrdered, snippet: '1. Primer paso\n2. Segundo paso\n' },
  { label: 'Cita', icon: Quote, snippet: '> Nota relevante\n' },
  { label: 'Link', icon: Link, snippet: '[Texto del enlace](https://example.com)' },
  { label: 'Boton CTA', icon: MousePointerClick, snippet: '<Button href="{{form_link}}">Completar formulario</Button>' },
  { label: 'Callout', icon: MessageSquareQuote, snippet: '<Callout type="info">\nTexto destacado\n</Callout>' },
  { label: 'Separador', icon: Minus, snippet: '<Divider />' },
  { label: 'Firma', icon: PenLine, snippet: '<Signature name="ServiGlobal IA" />' },
  { label: 'Resumen', icon: PenLine, snippet: '## Resumen de la llamada\n\n{{call_summary}}\n' },
];

export function EmailToolbar({ onInsert }: { onInsert: (snippet: string) => void }) {
  return (
    <div className="flex flex-wrap gap-2 rounded-md border border-border bg-muted/20 p-2">
      {TOOLS.map((tool) => {
        const Icon = tool.icon;
        return (
          <Button
            key={tool.label}
            type="button"
            size="sm"
            variant="outline"
            title={tool.label}
            aria-label={tool.label}
            onClick={() => onInsert(tool.snippet)}
            className="h-8 w-8 p-0"
          >
            <Icon className="h-4 w-4" />
          </Button>
        );
      })}
    </div>
  );
}
