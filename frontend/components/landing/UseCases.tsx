'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Headphones, LifeBuoy, DollarSign, Target, Briefcase, Calendar, ShoppingBag, ArrowRight, Sparkles } from 'lucide-react';
import Link from 'next/link';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

const VERTICAL_ICONS = {
  atencion: Headphones,
  soporte: LifeBuoy,
  cobranza: DollarSign,
  ventas: Target,
  reclutamiento: Briefcase,
  reservas: Calendar,
  ecommerce: ShoppingBag,
} as const;

const VERTICAL_IDS = ['atencion', 'soporte', 'cobranza', 'ventas', 'reclutamiento', 'reservas', 'ecommerce'] as const;

export function UseCases() {
  const t = useTranslations('useCases');
  const [activeId, setActiveId] = useState<typeof VERTICAL_IDS[number]>(VERTICAL_IDS[0]);
  const ActiveIcon = VERTICAL_ICONS[activeId];

  return (
    <section id="casos" className="py-24 bg-zinc-50 dark:bg-zinc-950 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <div className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-6">{t('title')}</h2>
          <p className="text-lg text-zinc-600 dark:text-neutral-400">{t('subtitle')}</p>
        </div>

        <div className="grid lg:grid-cols-12 gap-8">
          {/* Sidebar Menu */}
          <div className="lg:col-span-4 flex flex-col gap-2">
            {VERTICAL_IDS.map((id) => {
              const Icon = VERTICAL_ICONS[id];
              return (
                <button
                  suppressHydrationWarning
                  key={id}
                  onClick={() => setActiveId(id)}
                  className={cn(
                    "flex items-center gap-4 p-4 rounded-xl text-left transition-all duration-200 border",
                    activeId === id
                      ? "bg-violet-600/10 dark:bg-violet-600/10 border-violet-500/50 text-violet-900 dark:text-white shadow-lg"
                      : "bg-transparent border-transparent text-zinc-500 dark:text-neutral-400 hover:bg-black/5 dark:hover:bg-white/5 hover:text-black dark:hover:text-white"
                  )}
                >
                  <Icon className={cn("size-6", activeId === id ? "text-violet-600 dark:text-violet-400" : "text-zinc-400 dark:text-neutral-500")} />
                  <span className="font-semibold">{t(`verticals.${id}.title`)}</span>
                </button>
              );
            })}
          </div>

          {/* Content Card */}
          <div className="lg:col-span-8">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeId}
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                transition={{ duration: 0.3 }}
                className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 rounded-3xl p-8 md:p-12 h-full flex flex-col relative overflow-hidden shadow-2xl dark:shadow-none"
              >
                <div className="absolute top-0 right-0 p-32 bg-violet-500/5 dark:bg-violet-500/10 blur-[100px] rounded-full pointer-events-none" />
                
                <h3 className="text-3xl font-bold text-zinc-900 dark:text-white mb-4 flex items-center gap-3">
                   <ActiveIcon className="size-8 text-violet-600 dark:text-violet-500" />
                   {t(`verticals.${activeId}.title`)}
                </h3>
                <p className="text-xl text-violet-600 dark:text-violet-200 mb-8 font-medium">"{t(`verticals.${activeId}.promise`)}"</p>

                <div className="grid md:grid-cols-2 gap-8 mb-12">
                   <div>
                      <h4 className="text-sm font-semibold text-zinc-500 dark:text-neutral-500 uppercase tracking-wider mb-4">{t('automates')}</h4>
                      <ul className="space-y-3">
                        {(t.raw(`verticals.${activeId}.tasks`) as string[]).map((task, i) => (
                          <li key={i} className="flex items-start gap-2 text-zinc-700 dark:text-neutral-300">
                             <div className="mt-1.5 size-1.5 rounded-full bg-violet-500 dark:bg-violet-400" />
                             {task}
                          </li>
                        ))}
                      </ul>
                   </div>
                   <div>
                      <h4 className="text-sm font-semibold text-zinc-500 dark:text-neutral-500 uppercase tracking-wider mb-4">{t('typicalIntegrations')}</h4>
                       <div className="flex flex-wrap gap-2">
                         {(t.raw(`verticals.${activeId}.integrations`) as string[]).map((tool, i) => (
                           <span key={i} className="px-3 py-1 rounded-full bg-zinc-100 dark:bg-white/5 text-zinc-600 dark:text-neutral-300 text-sm border border-zinc-200 dark:border-white/5">
                             {tool}
                           </span>
                         ))}
                       </div>
                   </div>
                </div>

                {/* CTAs — Primary + Secondary (Regla 3.3, B3.1) */}
                <div className="mt-auto flex flex-col sm:flex-row gap-3">
                   <Link
                     href="#agendar"
                     className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-black dark:bg-white text-white dark:text-black font-bold hover:bg-violet-800 dark:hover:bg-violet-100 transition-colors"
                   >
                     {t('scheduleFor')} {t(`verticals.${activeId}.title`)}
                     <ArrowRight className="size-4" />
                   </Link>
                   <Link
                     href="#demos"
                     className="inline-flex items-center gap-2 px-6 py-3 rounded-lg border border-violet-300 dark:border-violet-500/30 text-violet-700 dark:text-violet-300 font-semibold hover:bg-violet-50 dark:hover:bg-violet-950/30 transition-colors"
                   >
                     <Sparkles className="size-4" />
                     {t('tryIAFor')} {t(`verticals.${activeId}.title`)}
                   </Link>
                </div>
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
      </div>
    </section>
  );
}
