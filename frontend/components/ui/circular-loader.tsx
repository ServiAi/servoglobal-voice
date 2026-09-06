'use client';

import React from 'react';

export type CircularLoaderSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl';
export type CircularLoaderVariant = 'disc' | 'ring';

export interface CircularLoaderProps {
  size?: CircularLoaderSize;
  variant?: CircularLoaderVariant;
  glow?: boolean;
  className?: string;
  label?: string;
  showLabel?: boolean;
  'aria-label'?: string;
}

const SIZE_MAP: Record<CircularLoaderSize, { container: string; glowBlur: string }> = {
  xs: { container: 'size-4', glowBlur: 'blur-[2px]' },
  sm: { container: 'size-5', glowBlur: 'blur-[3px]' },
  md: { container: 'size-8', glowBlur: 'blur-[6px]' },
  lg: { container: 'size-12', glowBlur: 'blur-[10px]' },
  xl: { container: 'size-16', glowBlur: 'blur-[14px]' },
  '2xl': { container: 'size-20', glowBlur: 'blur-[18px]' },
};

/**
 * CircularLoader reproduces the glowing conic-gradient circular loader:
 * - Conic gradient of cyan (#38bdf8), blue (#2563eb), violet (#7c3aed), magenta (#c084fc)
 * - Soft diffuse atmospheric glow in matching hues
 * - Smooth rotation (respects prefers-reduced-motion)
 */
export function CircularLoader({
  size = 'md',
  variant = 'disc',
  glow = true,
  className = '',
  label = 'Cargando…',
  showLabel = false,
  'aria-label': ariaLabel,
}: CircularLoaderProps) {
  const { container, glowBlur } = SIZE_MAP[size] ?? SIZE_MAP.md;
  const isRing = variant === 'ring';

  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={ariaLabel ?? label}
      className={`inline-flex flex-col items-center justify-center gap-2 ${className}`}
    >
      <div className={`relative flex items-center justify-center ${container} shrink-0`}>
        {/* Atmospheric ambient glow */}
        {glow && (
          <div
            aria-hidden="true"
            className={`circular-orb-gradient animate-circular-spin absolute inset-0 -m-[15%] rounded-full opacity-50 dark:opacity-75 ${glowBlur} transition-opacity duration-300 pointer-events-none`}
          />
        )}

        {/* Sharp core spinning orb */}
        <div
          aria-hidden="true"
          className={`circular-orb-gradient animate-circular-spin relative size-full rounded-full shadow-[0_3px_12px_rgba(37,99,235,0.24),0_1px_3px_rgba(15,23,42,0.08)] dark:shadow-[0_0_14px_rgba(56,189,248,0.5)]`}
        >
          {/* Inner cutout for 'ring' variant */}
          {isRing && (
            <div className="absolute inset-[18%] rounded-full bg-background dark:bg-zinc-950 shadow-inner" />
          )}
        </div>
      </div>

      {showLabel && (
        <span className="text-xs font-medium text-muted-foreground animate-pulse">
          {label}
        </span>
      )}
      <span className="sr-only">{ariaLabel ?? label}</span>
    </div>
  );
}

export interface CircularLoadingStateProps {
  message?: string;
  description?: string;
  minHeight?: string;
  size?: CircularLoaderSize;
  className?: string;
}

/**
 * Full component / panel / route loading screen with centered glowing orb.
 */
export function CircularLoadingState({
  message = 'Cargando información…',
  description,
  minHeight = 'min-h-[300px]',
  size = 'xl',
  className = '',
}: CircularLoadingStateProps) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label={message}
      className={`flex flex-col items-center justify-center p-8 text-center ${minHeight} ${className}`}
    >
      <div className="relative mb-5 flex items-center justify-center">
        {/* Enhanced ambient background bloom */}
        <div
          aria-hidden="true"
          className="absolute size-24 rounded-full bg-sky-500/15 blur-2xl dark:bg-cyan-500/20"
        />
        <div
          aria-hidden="true"
          className="absolute size-24 rounded-full bg-indigo-500/15 blur-2xl dark:bg-purple-500/20"
        />
        <CircularLoader size={size} glow={true} />
      </div>

      {message && (
        <p className="text-sm font-semibold tracking-tight text-foreground/90 sm:text-base">
          {message}
        </p>
      )}
      {description && (
        <p className="mt-1.5 max-w-sm text-xs text-muted-foreground">
          {description}
        </p>
      )}
      <span className="sr-only">{message}</span>
    </div>
  );
}

export interface CircularLoadingOverlayProps {
  active: boolean;
  message?: string;
  children: React.ReactNode;
  className?: string;
}

/**
 * Overlay for interactive panels during background mutations/fetching.
 */
export function CircularLoadingOverlay({
  active,
  message,
  children,
  className = '',
}: CircularLoadingOverlayProps) {
  return (
    <div className={`relative ${className}`}>
      {children}
      {active && (
        <div
          role="status"
          aria-busy="true"
          className="absolute inset-0 z-40 flex flex-col items-center justify-center bg-background/80 dark:bg-background/70 backdrop-blur-xs transition-opacity duration-200"
        >
          <CircularLoader size="lg" glow={true} label={message} showLabel={Boolean(message)} />
        </div>
      )}
    </div>
  );
}
