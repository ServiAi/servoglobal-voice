'use client';

import type { RefObject } from 'react';
import { EmailToolbar } from './EmailToolbar';

type Props = {
  value: string;
  onChange: (value: string) => void;
  onInsert: (snippet: string) => void;
  onPasteImages?: (files: File[]) => Promise<void>;
  textareaRef: RefObject<HTMLTextAreaElement>;
};

const EMOJIS = ['😀', '😊', '👍', '🎉', '✅', '🔥', '📌', '🤝'];

export function EmailMdxEditor({ value, onChange, onInsert, onPasteImages, textareaRef }: Props) {
  return (
    <div className="grid gap-2">
      <EmailToolbar onInsert={onInsert} />
      <div className="flex flex-wrap gap-1" aria-label="Emojis">
        {EMOJIS.map((emoji) => (
          <button
            key={emoji}
            type="button"
            className="h-8 w-8 rounded-md border border-border bg-background text-base hover:bg-muted"
            onClick={() => onInsert(emoji)}
            aria-label={`Insertar ${emoji}`}
          >
            {emoji}
          </button>
        ))}
      </div>
      <textarea
        ref={textareaRef}
        rows={18}
        className="min-h-[420px] rounded-md border border-border bg-background px-3 py-2 font-mono text-sm leading-6"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onPaste={(event) => {
          const images = Array.from(event.clipboardData.files).filter((file) => file.type.startsWith('image/'));
          if (images.length === 0 || !onPasteImages) return;
          event.preventDefault();
          void onPasteImages(images);
        }}
      />
    </div>
  );
}
