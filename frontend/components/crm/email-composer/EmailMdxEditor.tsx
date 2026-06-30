'use client';

import type { RefObject } from 'react';
import { EmailToolbar } from './EmailToolbar';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onInsert: (snippet: string) => void;
  textareaRef: RefObject<HTMLTextAreaElement>;
};

export function EmailMdxEditor({ value, onChange, onInsert, textareaRef }: Props) {
  return (
    <div className="grid gap-2">
      <EmailToolbar onInsert={onInsert} />
      <textarea
        ref={textareaRef}
        rows={18}
        className="min-h-[420px] rounded-md border border-border bg-background px-3 py-2 font-mono text-sm leading-6"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}
