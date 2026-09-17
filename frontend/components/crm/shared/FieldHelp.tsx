'use client';

import { useEffect, useRef, useState } from 'react';
import { HelpCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';

type Props = {
  align?: 'left' | 'right';
  label: string;
  required: boolean;
  children: string;
};

export function FieldHelp({ align = 'left', label, required, children }: Props) {
  const t = useTranslations('crm.fieldHelp');
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      const details = detailsRef.current;
      if (details && !details.contains(event.target as Node)) details.open = false;
    };
    document.addEventListener('pointerdown', closeOnOutsideClick);
    return () => document.removeEventListener('pointerdown', closeOnOutsideClick);
  }, [open]);

  return (
    <details ref={detailsRef} className="group relative inline-flex" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary
        className="inline-flex cursor-pointer list-none items-center text-muted-foreground hover:text-foreground focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden"
        aria-label={t('ariaLabel', { label })}
        title={t('ariaLabel', { label })}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          detailsRef.current?.toggleAttribute('open');
        }}
      >
        <HelpCircle className="h-3.5 w-3.5" aria-hidden="true" />
      </summary>
      <span className={`absolute top-5 z-50 w-72 max-w-[calc(100vw-2rem)] rounded-md border border-border bg-popover p-3 text-left text-xs font-normal text-popover-foreground shadow-md ${align === 'right' ? 'right-0' : 'left-0'}`}>
        <strong className="mb-1 block">{required ? t('required') : t('optional')}</strong>
        <span className="block leading-relaxed">{children}</span>
      </span>
    </details>
  );
}
