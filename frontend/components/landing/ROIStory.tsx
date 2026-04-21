'use client';

import { motion, useScroll, useTransform } from 'framer-motion';
import { useRef } from 'react';
import { BarChart3, CalendarCheck, Clock3, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

const ROI_ITEMS = [
  { key: 'response', icon: Clock3 },
  { key: 'agenda', icon: CalendarCheck },
  { key: 'workload', icon: Users },
  { key: 'coverage', icon: BarChart3 },
] as const;

export function ROIStory() {
  const t = useTranslations('roi');
  const containerRef = useRef<HTMLElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end start"]
  });

  const yLeft = useTransform(scrollYProgress, [0, 1], [-50, 50]);
  const yRight = useTransform(scrollYProgress, [0, 1], [50, -50]);
  const yBlob = useTransform(scrollYProgress, [0, 1], [80, -80]);

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
              {ROI_ITEMS.map(({ key, icon: Icon }) => (
                <div
                  key={key}
                  className="rounded-xl border border-zinc-200 dark:border-white/10 bg-white dark:bg-black/20 p-4"
                >
                  <div className="mb-4 flex size-10 items-center justify-center rounded-lg bg-violet-100 dark:bg-violet-950/40">
                    <Icon className="size-5 text-violet-700 dark:text-violet-300" />
                  </div>
                  <p className="font-semibold text-zinc-900 dark:text-white">
                    {t(`items.${key}.title`)}
                  </p>
                  <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-neutral-400">
                    {t(`items.${key}.description`)}
                  </p>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}
