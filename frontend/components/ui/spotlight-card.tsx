'use client';

import React, { ReactNode, useEffect, useRef } from 'react';

import { cn } from '@/lib/utils';

interface GlowCardProps {
  children?: ReactNode;
  className?: string;
  glowColor?: 'brand' | 'purple' | 'fuchsia' | 'violet' | 'red';
  size?: 'sm' | 'md' | 'lg';
  width?: string | number;
  height?: string | number;
  customSize?: boolean;
}

interface BrandSpotlightScopeProps {
  children: ReactNode;
  className?: string;
}

const glowColorMap = {
  brand: { base: 266, spread: 46 },
  purple: { base: 280, spread: 300 },
  fuchsia: { base: 292, spread: 36 },
  violet: { base: 262, spread: 42 },
  red: { base: 348, spread: 18 },
};

const sizeMap = {
  sm: 'w-48 h-64',
  md: 'w-64 h-80',
  lg: 'w-80 h-96',
};

function setSpotlightPosition(target: HTMLElement, x: number, y: number) {
  target.style.setProperty('--spotlight-x', x.toFixed(2));
  target.style.setProperty('--spotlight-y', y.toFixed(2));
  target.style.setProperty('--spotlight-xp', (x / window.innerWidth).toFixed(3));
  target.style.setProperty('--spotlight-yp', (y / window.innerHeight).toFixed(3));
}

export function BrandSpotlightScope({ children, className }: BrandSpotlightScopeProps) {
  const scopeRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const scope = scopeRef.current;

    if (!scope || window.matchMedia('(pointer: coarse)').matches) {
      return;
    }

    const syncPointer = (event: PointerEvent) => {
      setSpotlightPosition(scope, event.clientX, event.clientY);
    };

    window.addEventListener('pointermove', syncPointer, { passive: true });

    return () => {
      window.removeEventListener('pointermove', syncPointer);
    };
  }, []);

  return (
    <main ref={scopeRef} data-brand-spotlight-scope className={className}>
      {children}
    </main>
  );
}

export const GlowCard: React.FC<GlowCardProps> = ({
  children,
  className = '',
  glowColor = 'brand',
  size = 'md',
  width,
  height,
  customSize = false,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const { base, spread } = glowColorMap[glowColor];

  useEffect(() => {
    const syncPointer = (event: PointerEvent) => {
      if (cardRef.current) {
        setSpotlightPosition(cardRef.current, event.clientX, event.clientY);
      }
    };

    window.addEventListener('pointermove', syncPointer, { passive: true });

    return () => {
      window.removeEventListener('pointermove', syncPointer);
    };
  }, []);

  const inlineStyles: React.CSSProperties = {
    '--spotlight-base': base,
    '--spotlight-spread': spread,
    width: width === undefined ? undefined : typeof width === 'number' ? `${width}px` : width,
    height: height === undefined ? undefined : typeof height === 'number' ? `${height}px` : height,
  } as React.CSSProperties;

  return (
    <div
      ref={cardRef}
      data-glow
      style={inlineStyles}
      className={cn(
        !customSize && sizeMap[size],
        !customSize && 'aspect-[3/4]',
        'brand-spotlight-border relative grid grid-rows-[1fr_auto] gap-4 rounded-2xl border p-4 shadow-[0_1rem_2rem_-1rem_black] backdrop-blur-[5px]',
        className,
      )}
    >
      {children}
    </div>
  );
};
