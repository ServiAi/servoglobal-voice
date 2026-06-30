'use client';

import { Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';

type Props = {
  available: boolean;
  disabled: boolean;
  loadingFormat: 'md' | 'txt' | null;
  onAttach: (format: 'md' | 'txt') => void;
};

export function CallSummaryAttachmentButton({ available, disabled, loadingFormat, onAttach }: Props) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {(['md', 'txt'] as const).map((format) => (
        <Button
          key={format}
          type="button"
          size="sm"
          variant="outline"
          disabled={!available || disabled}
          onClick={() => onAttach(format)}
          className="justify-start gap-2"
        >
          <Paperclip className="h-4 w-4" />
          {loadingFormat === format ? 'Adjuntando...' : `Adjuntar .${format}`}
        </Button>
      ))}
    </div>
  );
}
