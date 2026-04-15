'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { ArrowRight, Check, FileText, Phone } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';

const PLAN_IDS = ['webConversion', 'voiceCloud', 'enterprise'] as const;

export function Pricing() {
  const t = useTranslations('pricing');

  return (
    <section id="precios" className="py-24 bg-white dark:bg-zinc-950 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center max-w-3xl mx-auto mb-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-6">
            {t('title')}
          </h2>
          <p className="text-lg text-zinc-600 dark:text-neutral-400">
            {t('subtitle')}
          </p>
        </motion.div>

        <div className="grid md:grid-cols-3 gap-6 lg:gap-8 mb-12">
          {PLAN_IDS.map((planId, idx) => {
            const isPopular = planId === 'voiceCloud';
            const isEnterprise = planId === 'enterprise';
            const features = t.raw(`plans.${planId}.features`) as string[];

            return (
              <motion.div
                key={planId}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
                className={cn(
                  'relative rounded-3xl p-8 border flex flex-col transition-all duration-300',
                  isPopular
                    ? 'bg-gradient-to-b from-violet-50 to-white dark:from-violet-950/30 dark:to-zinc-900 border-violet-300 dark:border-violet-500/40 shadow-xl shadow-violet-500/10 dark:shadow-violet-900/20 scale-[1.02]'
                    : 'bg-white dark:bg-zinc-900 border-zinc-200 dark:border-white/10 hover:border-violet-300 dark:hover:border-violet-500/30 shadow-sm dark:shadow-none'
                )}
              >
                {isPopular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2 px-4 py-1 bg-violet-600 text-white text-xs font-bold rounded-full uppercase tracking-wider">
                    {t('badgeRecommended')}
                  </div>
                )}

                <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">
                  {t(`plans.${planId}.name`)}
                </h3>
                <p className="text-sm text-zinc-500 dark:text-neutral-400 mb-6">
                  {t(`plans.${planId}.idealFor`)}
                </p>

                <div className="grid gap-3 mb-6">
                  <div className="rounded-2xl bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 p-4">
                    <p className="text-xs uppercase tracking-wider font-semibold text-zinc-500 dark:text-neutral-500 mb-1">
                      {t('setupLabel')}
                    </p>
                    <p className="text-2xl font-bold text-zinc-900 dark:text-white">
                      {t(`plans.${planId}.setup`)}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-zinc-50 dark:bg-black/20 border border-zinc-200 dark:border-white/10 p-4">
                    <p className="text-xs uppercase tracking-wider font-semibold text-zinc-500 dark:text-neutral-500 mb-1">
                      {t('monthlyFeeLabel')}
                    </p>
                    <p className="text-3xl font-bold text-zinc-900 dark:text-white">
                      {t(`plans.${planId}.monthly`)}
                    </p>
                    {!isEnterprise && (
                      <p className="text-xs text-zinc-500 dark:text-neutral-500 mt-1">
                        {t('monthlyFeeHelp')}
                      </p>
                    )}
                  </div>
                  <div className="rounded-2xl bg-violet-50 dark:bg-violet-950/20 border border-violet-200 dark:border-violet-500/20 p-4">
                    <p className="text-xs uppercase tracking-wider font-semibold text-violet-700 dark:text-violet-300 mb-1">
                      {t('includedMinutesLabel')}
                    </p>
                    <p className="text-base font-bold text-zinc-900 dark:text-white">
                      {t(`plans.${planId}.minutes`)}
                    </p>
                  </div>
                </div>

                <ul className="space-y-3 mb-8 flex-1">
                  {features.map((feature, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-neutral-300">
                      <Check className="size-4 text-violet-500 mt-0.5 shrink-0" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                {isEnterprise ? (
                  <Link
                    href="#agendar"
                    className="w-full text-center py-3 px-6 rounded-xl font-bold transition-all flex items-center justify-center gap-2 bg-violet-600 text-white hover:bg-violet-700 shadow-lg shadow-violet-500/20 cursor-pointer"
                  >
                    <Phone className="size-4" />
                    {t('salesCta')}
                  </Link>
                ) : (
                  <Link
                    href="#agendar"
                    className={cn(
                      'w-full text-center py-3 px-6 rounded-xl font-bold transition-all flex items-center justify-center gap-2',
                      isPopular
                        ? 'bg-violet-600 text-white hover:bg-violet-700 shadow-lg shadow-violet-500/20'
                        : 'bg-zinc-100 dark:bg-white/5 text-zinc-900 dark:text-white border border-zinc-200 dark:border-white/10 hover:bg-violet-50 dark:hover:bg-violet-950/30'
                    )}
                  >
                    {t('cta')}
                    <ArrowRight className="size-4" />
                  </Link>
                )}
              </motion.div>
            );
          })}
        </div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-5xl mx-auto"
        >
          <div className="rounded-2xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900 p-6 md:p-8 shadow-sm">
            <div className="flex flex-col md:flex-row gap-6">
              <div className="flex items-start gap-3 md:w-72 shrink-0">
                <div className="size-11 rounded-lg bg-violet-100 dark:bg-violet-950/40 flex items-center justify-center shrink-0">
                  <FileText className="size-6 text-violet-600 dark:text-violet-300" />
                </div>
                <div>
                  <h3 className="text-xl font-bold text-zinc-900 dark:text-white">
                    {t('commercialTerms.title')}
                  </h3>
                  <p className="text-sm text-zinc-600 dark:text-neutral-400 mt-1">
                    {t('commercialTerms.description')}
                  </p>
                </div>
              </div>

              <ul className="grid sm:grid-cols-2 gap-3 flex-1">
                {(t.raw('commercialTerms.items') as string[]).map((item, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-neutral-300">
                    <Check className="size-4 text-violet-500 mt-0.5 shrink-0" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </motion.div>

        <p className="text-center text-sm text-zinc-500 dark:text-neutral-600 mt-12 max-w-2xl mx-auto">
          {t('consumptionNote')}
        </p>
      </div>
    </section>
  );
}
