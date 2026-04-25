'use client';

import { motion } from 'framer-motion';
import { useRef } from 'react';
import { BarChart3, CalendarCheck, Clock3, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  sectionDesktop,
  useParallaxLayer,
  useSectionParallax,
} from '@/hooks/useSectionParallax';

const ROI_ITEMS = [
  { key: 'response', icon: Clock3, color: 'cyan' },
  { key: 'agenda', icon: CalendarCheck, color: 'emerald' },
  { key: 'workload', icon: Users, color: 'violet' },
  { key: 'coverage', icon: BarChart3, color: 'amber' },
] as const;

const roiColorMap: Record<string, { bg: string; icon: string; glow: string }> = {
  cyan: {
    bg: 'bg-cyan-100 dark:bg-cyan-950/60',
    icon: 'text-cyan-600 dark:text-cyan-400',
    glow: 'shadow-md shadow-cyan-200/50 dark:shadow-cyan-500/20',
  },
  emerald: {
    bg: 'bg-emerald-100 dark:bg-emerald-950/60',
    icon: 'text-emerald-600 dark:text-emerald-400',
    glow: 'shadow-md shadow-emerald-200/50 dark:shadow-emerald-500/20',
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
};

export function ROIStory() {
  const t = useTranslations('roi');
  const containerRef = useRef<HTMLElement>(null);

  const { profile, scrollYProgress } = useSectionParallax({
    target: containerRef,
    desktopProfile: sectionDesktop,
  });
  const yLeft = useParallaxLayer(scrollYProgress, profile, 'content');
  const yRight = useParallaxLayer(scrollYProgress, profile, 'accent');
  const yBlob = useParallaxLayer(scrollYProgress, profile, 'background', -1);

  return (
    <section ref={containerRef} className="relative py-24 bg-white dark:bg-zinc-950 border-b border-zinc-200 dark:border-white/5 transition-colors duration-300 overflow-hidden">
      {/* Decorative Parallax Blob */}
      <motion.div style={{ y: yBlob }} className="absolute top-1/4 -left-20 w-80 h-80 bg-violet-600/5 dark:bg-violet-600/10 rounded-full blur-[100px] pointer-events-none -z-10" />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-center"
        >
          <motion.div style={{ y: yLeft }}>
            <p className="text-sm font-semibold uppercase tracking-wider text-violet-700 dark:text-violet-300">
              {t('eyebrow')}
            </p>
            <h2 className="mt-3 text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white">
              {t('title')}
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-zinc-600 dark:text-neutral-400">
              {t('description')}
            </p>
          </motion.div>

          <motion.div style={{ y: yRight }} className="rounded-3xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-zinc-900 p-6 md:p-8">
            <h3 className="text-xl font-bold text-zinc-900 dark:text-white">
              {t('boxTitle')}
            </h3>
            <div className="mt-6 grid gap-4 sm:grid-cols-2">
              {ROI_ITEMS.map(({ key, icon: Icon, color }) => {
                const colors = roiColorMap[color];
                return (
                <div
                  key={key}
                  className="rounded-xl border border-zinc-200 dark:border-white/10 bg-white dark:bg-black/20 p-4"
                >
                  <div className={`mb-4 flex size-10 items-center justify-center rounded-lg ${colors.bg} ${colors.glow}`}>
                    <Icon className={`size-5 ${colors.icon}`} />
                  </div>
                  <p className="font-semibold text-zinc-900 dark:text-white">
                    {t(`items.${key}.title`)}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-neutral-400">
                    {t(`items.${key}.description`)}
                  </p>
                </div>
              );
              })}
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
