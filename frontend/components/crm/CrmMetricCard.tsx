'use client';

import React from 'react';
import { Card } from '../ui/card';
import { LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

type CrmMetricCardProps = {
  title: string;
  value: string | number;
  icon?: LucideIcon;
  subtext?: string;
  className?: string;
  iconClassName?: string;
};

export function CrmMetricCard({
  title,
  value,
  icon: Icon,
  subtext,
  className,
  iconClassName,
}: CrmMetricCardProps) {
  return (
    <Card className={cn('p-6 relative overflow-hidden transition-all duration-300 hover:shadow-md border border-border bg-card', className)}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {title}
        </span>
        {Icon && (
          <div className={cn('p-2 rounded-lg bg-muted text-muted-foreground', iconClassName)}>
            <Icon className="h-4 w-4" />
          </div>
        )}
      </div>
      <div className="mt-4 flex items-baseline gap-2">
        <span className="text-2xl font-bold tracking-tight text-foreground">
          {value}
        </span>
      </div>
      {subtext && (
        <p className="mt-2 text-xs text-muted-foreground">
          {subtext}
        </p>
      )}
    </Card>
  );
}
