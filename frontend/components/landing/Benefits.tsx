'use client';

import { motion } from 'framer-motion';
import { useRef } from 'react';
import { TrendingUp, Clock, ShieldCheck, Banknote, Workflow, Rocket, Zap, Lock } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  sectionDesktop,
  useParallaxLayer,
  useSectionParallax,
} from '@/hooks/useSectionParallax';

const BENEFIT_ICONS = [TrendingUp, Clock, ShieldCheck, Banknote, Workflow, Rocket, Zap, Lock];
const BENEFIT_KEYS = ['sales', 'service', 'errors', 'costs', 'stack', 'time', 'superPlus', 'security'] as const;

export function Benefits() {
  const t = useTranslations('benefits');
  const containerRef = useRef<HTMLElement>(null);
  
  const { profile, scrollYProgress } = useSectionParallax({
    target: containerRef,
    desktopProfile: sectionDesktop,
  });
  const yBlob = useParallaxLayer(scrollYProgress, profile, 'background', -1);
  const yTitle = useParallaxLayer(scrollYProgress, profile, 'content');
  const yCards = useParallaxLayer(scrollYProgress, profile, 'accent');

  return (
    <section ref={containerRef} className="relative py-24 bg-zinc-50 dark:bg-black border-y border-black/5 dark:border-white/5 transition-colors duration-300 overflow-hidden z-0">
      <motion.div
        style={{ y: yBlob }}
        className="absolute -top-20 right-0 w-[28rem] h-[28rem] rounded-full bg-violet-600/5 dark:bg-violet-600/10 blur-[110px] pointer-events-none -z-10"
      />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <motion.div style={{ y: yTitle }} className="mb-16 text-center">
            <h2 className="text-3xl font-bold text-zinc-900 dark:text-white mb-4">{t('title')}</h2>
            <p className="text-zinc-600 dark:text-neutral-400">{t('subtitle')}</p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 sm:gap-8">
          {BENEFIT_KEYS.map((key, i) => {
            const Icon = BENEFIT_ICONS[i];
            const isSuperPlus = key === 'superPlus';
            return (
             <motion.div
               key={key}
               style={{ y: yCards }}
               className={`${
                 isSuperPlus
                   ? 'bg-gradient-to-br from-violet-50 to-fuchsia-50 dark:from-violet-950/20 dark:to-fuchsia-950/20 border-violet-200 dark:border-violet-500/20'
                   : 'bg-white dark:bg-white/5 border-zinc-200 dark:border-white/5'
               } border p-8 rounded-2xl hover:bg-zinc-100 dark:hover:bg-white/10 transition-colors group shadow-sm dark:shadow-none relative`}
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
             </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
