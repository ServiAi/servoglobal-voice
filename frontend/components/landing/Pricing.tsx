'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { Check, Zap, ArrowRight, Settings, Phone } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';

const PLAN_IDS = ['conecta', 'integra', 'escala'] as const;

const PLAN_HIGHLIGHTS: Record<string, string[]> = {
  conecta: [
    '1,000 min Click-to-IA-Call (Web)',
    '300 min Entrantes (DID)',
    '0 min Salientes (Consumo)',
    'DID no incluido (Add-on)',
    '1 caso de uso / flujo esencial',
    'Notificaciones (SMS/WhatsApp)'
  ],
  integra: [
    '3,000 min Click-to-IA-Call (Web)',
    '1,000 min Entrantes (DID)',
    '300 min Salientes (Outbound)',
    '1 DID incluido (Local/USA)',
    'Hasta 3 casos de uso',
    'Soporte Omnicanal + Grabación'
  ],
  escala: [
    '8,000 min Click-to-IA-Call (Web)',
    '2,500 min Entrantes (DID)',
    '800 min Salientes (Outbound)',
    'Programador Saliente (Batch + Reintentos)',
    'Flujos ilimitados + API',
    'Handoff Contact Center'
  ],
};

export function Pricing() {
  const t = useTranslations('pricing');

  return (
    <section id="precios" className="py-24 bg-white dark:bg-zinc-950 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        {/* Header */}
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

        {/* Plans Grid */}
        <div className="grid md:grid-cols-3 gap-6 lg:gap-8 mb-16">
          {PLAN_IDS.map((planId, idx) => {
            const isPopular = idx === 1;
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
                    Recomendado
                  </div>
                )}

                {/* Plan Name */}
                <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">
                  {t(`plans.${planId}.name`)}
                </h3>
                <p className="text-sm text-zinc-500 dark:text-neutral-400 mb-6">
                  {t(`plans.${planId}.idealFor`)}
                </p>

                {/* Pricing */}
                <div className="mb-6">
                  <div className="flex items-baseline gap-1 mb-1">
                    <span className="text-sm text-zinc-500 dark:text-neutral-500">{t('from')}</span>
                    <span className="text-4xl font-bold text-zinc-900 dark:text-white">
                      {t(`plans.${planId}.monthly`)}
                    </span>
                    <span className="text-sm text-zinc-500 dark:text-neutral-500">/ {t('monthly').toLowerCase()}</span>
                  </div>
                  <p className="text-sm text-zinc-500 dark:text-neutral-500">
                    {t('setup')}: {t('from')} {t(`plans.${planId}.setup`)}
                  </p>
                </div>

                {/* Features */}
                <ul className="space-y-3 mb-8 flex-1">
                  {PLAN_HIGHLIGHTS[planId].map((feat, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-neutral-300">
                      <Check className="size-4 text-violet-500 mt-0.5 shrink-0" />
                      {feat}
                    </li>
                  ))}
                </ul>

                {/* Excess Rates Mini-Table per Plan (Optional, but user asked for it in card? No, "linea final: Excesos") */}
                <div className="border-t border-zinc-100 dark:border-white/5 pt-4 mb-6">
                    <p className="text-xs text-zinc-500 dark:text-neutral-500 font-semibold mb-1">Excesos:</p>
                    <div className="text-xs text-zinc-500 dark:text-neutral-500 space-y-0.5">
                        <div className="flex justify-between"><span>Web:</span><span>$0.09/min</span></div>
                        <div className="flex justify-between"><span>DID:</span><span>$0.10/min</span></div>
                        <div className="flex justify-between"><span>Out:</span><span>$0.14/min</span></div>
                    </div>
                </div>


                {/* CTA */}
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
              </motion.div>
            );
          })}
        </div>

        {/* Add-on: Super Plus */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="max-w-4xl mx-auto mb-16"
        >
          <div className="relative overflow-hidden rounded-2xl border border-amber-200 dark:border-amber-500/30 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-950/20 dark:to-orange-950/20 p-8">
            <div className="flex flex-col md:flex-row items-center gap-8">
              <div className="flex-1">
                <div className="flex items-center gap-3 mb-2">
                   <div className="size-10 rounded-lg bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center shrink-0">
                    <Zap className="size-6 text-amber-600 dark:text-amber-400" />
                  </div>
                  <h3 className="text-xl font-bold text-zinc-900 dark:text-white">
                    {t('addon.name')}
                  </h3>
                </div>
                
                <p className="text-zinc-700 dark:text-neutral-300 mb-4">
                  {t('addon.description')}
                </p>
                <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                  <span className="text-zinc-900 dark:text-white font-medium">
                    {t('monthly')}: {t('from')} {t('addon.monthly')}
                  </span>
                  <span className="text-zinc-600 dark:text-neutral-400">
                    {t('setup')}: {t('from')} {t('addon.setup')}
                  </span>
                </div>
              </div>
              <div className="shrink-0">
                <Link
                  href="#demo-voice"
                  className="inline-flex items-center justify-center px-6 py-2.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-white font-medium transition-colors"
                >
                  Probar Demo
                  <ArrowRight className="ml-2 size-4" />
                </Link>
              </div>
            </div>
          </div>
        </motion.div>

        {/* Professional Services */}
        <motion.div
           initial={{ opacity: 0, y: 20 }}
           whileInView={{ opacity: 1, y: 0 }}
           viewport={{ once: true }}
           className="max-w-4xl mx-auto"
        >
           <h3 className="text-2xl font-bold text-center text-zinc-900 dark:text-white mb-8">
            {t('services.byopbx.header')}
           </h3>
           <div className="bg-blue-100 dark:bg-blue-900/40 rounded-2xl border border-blue-200 dark:border-blue-800 p-8 shadow-sm">
              <div className="flex flex-col md:flex-row gap-6 items-start">
                  <div className="size-12 rounded-xl bg-blue-100 dark:bg-blue-900/20 flex items-center justify-center shrink-0">
                    <Settings className="size-6 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div className="flex-1">
                      <h4 className="text-lg font-bold text-zinc-900 dark:text-white mb-2">
                        {t('services.byopbx.name')}
                      </h4>
                      <p className="text-zinc-600 dark:text-neutral-400 mb-4">
                        {t('services.byopbx.description')}
                      </p>
                      <div className="grid sm:grid-cols-2 gap-4">
                          <div className="flex items-start gap-2 text-sm">
                              <Check className="size-4 text-blue-500 mt-0.5" />
                              <span className="text-zinc-700 dark:text-neutral-300">{t('services.byopbx.assessment')}</span>
                          </div>
                          <div className="flex items-start gap-2 text-sm">
                              <Check className="size-4 text-blue-500 mt-0.5" />
                              <span className="text-zinc-700 dark:text-neutral-300">{t('services.byopbx.setup')}</span>
                          </div>
                      </div>
                  </div>
                  <div className="shrink-0 flex items-center">
                    <Link
                      href="#contact"
                      className="text-blue-600 dark:text-blue-400 font-medium hover:underline flex items-center gap-1"
                    >
                      Solicitar cotización <ArrowRight className="size-4" />
                    </Link>
                  </div>
              </div>
           </div>
        </motion.div>

        {/* Consumption Note */}
        <p className="text-center text-sm text-zinc-500 dark:text-neutral-600 mt-12 max-w-lg mx-auto">
          {t('consumptionNote')}
        </p>
      </div>
    </section>
  );
}
