'use client';

import { motion } from 'framer-motion';
import { useRef } from 'react';
import { ArrowRight, Briefcase, CalendarCheck, CheckCircle2, Headphones, ShoppingBag, Sparkles, Target } from 'lucide-react';
import Link from 'next/link';
import { useTranslations } from 'next-intl';
import {
  sectionDesktop,
  useParallaxLayer,
  useSectionParallax,
} from '@/hooks/useSectionParallax';

const RESULT_IDS = ['scheduling', 'leads', 'triage'] as const;
const PRIORITY_VERTICAL_IDS = ['realEstateLeads', 'healthBooking', 'collectionsRecovery'] as const;
const OTHER_SECTOR_IDS = ['atencion', 'soporte', 'ventas', 'reclutamiento', 'ecommerce'] as const;

const RESULT_ICONS = {
  scheduling: { icon: CalendarCheck, color: 'blue' },
  leads: { icon: Target, color: 'violet' },
  triage: { icon: Headphones, color: 'cyan' },
} as const;

const SECTOR_ICONS = {
  atencion: { icon: Headphones, color: 'emerald' },
  soporte: { icon: CheckCircle2, color: 'blue' },
  cobranza: { icon: Sparkles, color: 'rose' },
  ventas: { icon: Target, color: 'amber' },
  reclutamiento: { icon: Briefcase, color: 'violet' },
  reservas: { icon: CalendarCheck, color: 'cyan' },
  ecommerce: { icon: ShoppingBag, color: 'rose' },
} as const;

const PRIORITY_ICONS = {
  realEstateLeads: { icon: Briefcase, color: 'amber' },
  healthBooking: { icon: CalendarCheck, color: 'emerald' },
  collectionsRecovery: { icon: Sparkles, color: 'rose' },
} as const;

const ucColorMap: Record<string, { bg: string; icon: string; glow: string }> = {
  emerald: {
    bg: 'bg-emerald-100 dark:bg-emerald-950/60',
    icon: 'text-emerald-600 dark:text-emerald-400',
    glow: 'shadow-md shadow-emerald-200/50 dark:shadow-emerald-500/20',
  },
  blue: {
    bg: 'bg-blue-100 dark:bg-blue-950/60',
    icon: 'text-blue-600 dark:text-blue-400',
    glow: 'shadow-md shadow-blue-200/50 dark:shadow-blue-500/20',
  },
  violet: {
    bg: 'bg-violet-100 dark:bg-violet-950/60',
    icon: 'text-violet-600 dark:text-violet-400',
    glow: 'shadow-md shadow-violet-200/50 dark:shadow-violet-500/20',
  },
  amber: {
    bg: 'bg-amber-100 dark:bg-amber-950/60',
    icon: 'text-amber-600 dark:text-amber-400',
    glow: 'shadow-md shadow-amber-200/50 dark:shadow-amber-500/20',
  },
  rose: {
    bg: 'bg-rose-100 dark:bg-rose-950/60',
    icon: 'text-rose-600 dark:text-rose-400',
    glow: 'shadow-md shadow-rose-200/50 dark:shadow-rose-500/20',
  },
  cyan: {
    bg: 'bg-cyan-100 dark:bg-cyan-950/60',
    icon: 'text-cyan-600 dark:text-cyan-400',
    glow: 'shadow-md shadow-cyan-200/50 dark:shadow-cyan-500/20',
  },
};

export function UseCases() {
  const t = useTranslations('useCases');
  const containerRef = useRef<HTMLElement>(null);
  
  const { profile, scrollYProgress } = useSectionParallax({
    target: containerRef,
    desktopProfile: sectionDesktop,
  });
  const yTitle = useParallaxLayer(scrollYProgress, profile, 'content');
  const yFloating1 = useParallaxLayer(scrollYProgress, profile, 'background');
  const yFloating2 = useParallaxLayer(scrollYProgress, profile, 'background', -1);
  const yPriority = useParallaxLayer(scrollYProgress, profile, 'accent');
  const yResults = useParallaxLayer(scrollYProgress, profile, 'accent');
  const ySectors = useParallaxLayer(scrollYProgress, profile, 'content');

  return (
    <section ref={containerRef} id="casos" className="relative py-24 bg-zinc-50 dark:bg-zinc-950 transition-colors duration-300 overflow-hidden z-0">
      
      {/* Decorative Parallax Backgrounds */}
      <motion.div style={{ y: yFloating1 }} className="absolute -top-10 -left-20 w-96 h-96 bg-violet-600/5 dark:bg-violet-600/10 rounded-full blur-[100px] -z-10 pointer-events-none" />
      <motion.div style={{ y: yFloating2 }} className="absolute bottom-20 -right-20 w-[30rem] h-[30rem] bg-fuchsia-600/5 dark:bg-fuchsia-600/10 rounded-full blur-[120px] -z-10 pointer-events-none" />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <motion.div style={{ y: yTitle }} className="text-center max-w-3xl mx-auto mb-14">
          <h2 className="text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-6">
            {t('title')}
          </h2>
          <p className="text-lg text-zinc-600 dark:text-neutral-400">
            {t('subtitle')}
          </p>
        </motion.div>

        <motion.div style={{ y: yPriority }} className="mb-16">
          <div className="mb-7 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-sm font-semibold uppercase tracking-wider text-violet-700 dark:text-violet-300">
                {t('priorityEyebrow')}
              </p>
              <h3 className="mt-2 text-2xl md:text-3xl font-bold text-zinc-900 dark:text-white">
                {t('priorityTitle')}
              </h3>
            </div>
            <p className="max-w-2xl text-sm md:text-base text-zinc-600 dark:text-neutral-400">
              {t('prioritySubtitle')}
            </p>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            {PRIORITY_VERTICAL_IDS.map((id, idx) => {
              const { icon: Icon, color } = PRIORITY_ICONS[id];
              const colors = ucColorMap[color];
              const tasks = t.raw(`priorityVerticals.${id}.tasks`) as string[];

              return (
                <motion.article
                  key={id}
                  initial={{ opacity: 0, y: 24 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: idx * 0.1 }}
                  className="rounded-3xl border border-violet-200 dark:border-violet-500/20 bg-white dark:bg-zinc-900 p-7 shadow-sm dark:shadow-none"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className={`size-12 rounded-xl ${colors.bg} ${colors.glow} flex items-center justify-center`}>
                      <Icon className={`size-6 ${colors.icon}`} />
                    </div>
                    <span className="rounded-full bg-zinc-100 dark:bg-white/5 px-3 py-1 text-xs font-semibold text-zinc-600 dark:text-neutral-300">
                      {t('priorityBadge')}
                    </span>
                  </div>
                  <h3 className="mt-5 text-xl font-bold text-zinc-900 dark:text-white">
                    {t(`priorityVerticals.${id}.title`)}
                  </h3>
                  <p className="mt-3 text-sm leading-relaxed text-zinc-600 dark:text-neutral-400">
                    {t(`priorityVerticals.${id}.promise`)}
                  </p>
                  <ul className="mt-5 space-y-3">
                    {tasks.map((task, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-neutral-300">
                        <span className="mt-1.5 size-1.5 rounded-full bg-violet-500 dark:bg-violet-400 shrink-0" />
                        <span>{task}</span>
                      </li>
                    ))}
                  </ul>
                </motion.article>
              );
            })}
          </div>
        </motion.div>

        <motion.div style={{ y: yResults }} className="mb-8 text-center">
          <h3 className="text-2xl md:text-3xl font-bold text-zinc-900 dark:text-white">
            {t('resultsTitle')}
          </h3>
          <p className="mt-3 text-zinc-600 dark:text-neutral-400">
            {t('resultsSubtitle')}
          </p>
        </motion.div>

        <motion.div style={{ y: yResults }} className="grid md:grid-cols-3 gap-6 lg:gap-8 mb-14">
          {RESULT_IDS.map((id, idx) => {
            const { icon: Icon, color } = RESULT_ICONS[id];
            const colors = ucColorMap[color];
            const tasks = t.raw(`results.${id}.tasks`) as string[];
            const href = id === 'scheduling' ? '#agendar' : '#demos';

            return (
              <motion.article
                key={id}
                initial={{ opacity: 0, y: 24 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: idx * 0.1 }}
                className="bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-white/10 rounded-3xl p-7 flex flex-col shadow-sm dark:shadow-none hover:border-violet-300 dark:hover:border-violet-500/30 transition-colors"
              >
                <div className={`size-12 rounded-xl ${colors.bg} ${colors.glow} flex items-center justify-center mb-5`}>
                  <Icon className={`size-6 ${colors.icon}`} />
                </div>
                <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-3">
                  {t(`results.${id}.title`)}
                </h3>
                <p className="text-zinc-600 dark:text-neutral-400 mb-6">
                  {t(`results.${id}.promise`)}
                </p>
                <ul className="space-y-3 mb-8 flex-1">
                  {tasks.map((task, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-zinc-700 dark:text-neutral-300">
                      <span className="mt-1.5 size-1.5 rounded-full bg-violet-500 dark:bg-violet-400 shrink-0" />
                      <span>{task}</span>
                    </li>
                  ))}
                </ul>
                <Link
                  href={href}
                  className="inline-flex items-center justify-center gap-2 px-5 py-3 rounded-lg bg-black dark:bg-white text-white dark:text-black font-bold hover:bg-violet-800 dark:hover:bg-violet-100 transition-colors"
                >
                  {t(`results.${id}.cta`)}
                  <ArrowRight className="size-4" />
                </Link>
              </motion.article>
              );
            })}
        </motion.div>

        <motion.div
          style={{ y: ySectors }}
          initial={{ opacity: 0, scale: 0.98 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true }}
          className="rounded-3xl border border-zinc-200 dark:border-white/10 bg-white dark:bg-zinc-900 p-6 md:p-8"
        >
          <div className="flex flex-col md:flex-row md:items-end md:justify-between gap-4 mb-6">
            <div>
              <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">
                {t('sectorsTitle')}
              </h3>
              <p className="text-zinc-600 dark:text-neutral-400 max-w-2xl">
                {t('sectorsSubtitle')}
              </p>
            </div>
            <Link
              href="#agendar"
              className="inline-flex items-center gap-2 text-violet-700 dark:text-violet-300 font-semibold hover:underline"
            >
              {t('sectorCta')}
              <ArrowRight className="size-4" />
            </Link>
          </div>

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {OTHER_SECTOR_IDS.map((id) => {
              const { icon: Icon, color } = SECTOR_ICONS[id];
              const colors = ucColorMap[color];
              return (
                <div
                  key={id}
                  className="rounded-xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-black/20 p-4"
                >
                  <div className={`size-9 rounded-lg ${colors.bg} ${colors.glow} flex items-center justify-center mb-3`}>
                    <Icon className={`size-5 ${colors.icon}`} />
                  </div>
                  <p className="font-semibold text-zinc-900 dark:text-white text-sm">
                    {t(`verticals.${id}.title`)}
                  </p>
                  <p className="text-xs text-zinc-600 dark:text-neutral-400 mt-2">
                    {t(`verticals.${id}.promise`)}
                  </p>
                </div>
              );
            })}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
