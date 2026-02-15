'use client';

import { TrendingUp, Clock, ShieldCheck, Banknote, Workflow, Rocket, Zap, Lock } from 'lucide-react';
import { useTranslations } from 'next-intl';

const BENEFIT_ICONS = [TrendingUp, Clock, ShieldCheck, Banknote, Workflow, Rocket, Zap, Lock];
const BENEFIT_KEYS = ['sales', 'service', 'errors', 'costs', 'stack', 'time', 'superPlus', 'security'] as const;

export function Benefits() {
  const t = useTranslations('benefits');

  return (
    <section className="py-24 bg-zinc-50 dark:bg-black border-y border-black/5 dark:border-white/5 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <div className="mb-16 text-center">
            <h2 className="text-3xl font-bold text-zinc-900 dark:text-white mb-4">{t('title')}</h2>
            <p className="text-zinc-600 dark:text-neutral-400">{t('subtitle')}</p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 sm:gap-8">
          {BENEFIT_KEYS.map((key, i) => {
            const Icon = BENEFIT_ICONS[i];
            const isSuperPlus = key === 'superPlus';
            return (
             <div
               key={key}
               className={`${
                 isSuperPlus
                   ? 'bg-gradient-to-br from-violet-50 to-fuchsia-50 dark:from-violet-950/20 dark:to-fuchsia-950/20 border-violet-200 dark:border-violet-500/20'
                   : 'bg-white dark:bg-white/5 border-zinc-200 dark:border-white/5'
               } border p-8 rounded-2xl hover:bg-zinc-100 dark:hover:bg-white/10 transition-colors group shadow-sm dark:shadow-none`}
             >
                <div className={`size-12 rounded-lg ${
                  isSuperPlus
                    ? 'bg-violet-100 dark:bg-violet-900/30'
                    : 'bg-violet-100 dark:bg-violet-900/30'
                } flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}>
                   <Icon className={`size-6 ${
                     isSuperPlus
                       ? 'text-fuchsia-600 dark:text-fuchsia-400'
                       : 'text-violet-600 dark:text-violet-400'
                   }`} />
                </div>
                <h3 className="text-xl font-bold text-zinc-900 dark:text-white mb-3">{t(`items.${key}.title`)}</h3>
                <p className="text-zinc-600 dark:text-neutral-400 leading-relaxed text-sm">
                   {t(`items.${key}.desc`)}
                </p>
             </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
