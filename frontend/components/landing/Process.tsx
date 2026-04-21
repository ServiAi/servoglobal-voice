'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { useRef } from 'react';
import { useTranslations } from 'next-intl';
import {
  sectionDesktop,
  useParallaxLayer,
  useSectionParallax,
} from '@/hooks/useSectionParallax';

const PHASE_IDS = ['phase1', 'phase2', 'phase3'] as const;

export function Process() {
  const t = useTranslations('process');
  const containerRef = useRef<HTMLElement>(null);

  const { profile, scrollYProgress } = useSectionParallax({
    target: containerRef,
    desktopProfile: sectionDesktop,
  });
  const yTitle = useParallaxLayer(scrollYProgress, profile, 'content');
  const yBlob = useParallaxLayer(scrollYProgress, profile, 'background', -1);
  const yPhase = useParallaxLayer(scrollYProgress, profile, 'accent');

  return (
    <section ref={containerRef} id="como-funciona" className="relative py-24 bg-white dark:bg-zinc-950 transition-colors duration-300 overflow-hidden">
      {/* Decorative Parallax Blob */}
      <motion.div style={{ y: yBlob }} className="absolute top-1/3 left-1/2 -translate-x-1/2 w-[40rem] h-[40rem] bg-violet-600/5 dark:bg-violet-600/10 rounded-full blur-[140px] pointer-events-none -z-10" />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <motion.div style={{ y: yTitle }} className="text-center max-w-3xl mx-auto mb-16">
          <h2 className="text-3xl font-bold mb-4 text-zinc-900 dark:text-white">{t('title')}</h2>
          <p className="text-xl text-violet-600 dark:text-violet-400 font-medium mb-4">{t('subtitle')}</p>
          <p className="text-zinc-600 dark:text-neutral-400">{t('description')}</p>
          <p className="text-xs text-zinc-500 dark:text-neutral-500 mt-3">{t('microcopySetup')}</p>
        </motion.div>

        <div className="relative grid md:grid-cols-3 gap-8">
           {/* Connecting Line (Desktop) */}
           <div className="hidden md:block absolute top-12 left-[16%] right-[16%] h-0.5 bg-gradient-to-r from-violet-200 via-violet-500 to-violet-200 dark:from-violet-900 dark:via-violet-500 dark:to-violet-900 z-0 opacity-30" />

           {PHASE_IDS.map((phaseId) => (
             <motion.div key={phaseId} style={{ y: yPhase }} className="relative z-10 flex flex-col items-center text-center">
               <div className="size-24 rounded-2xl bg-white dark:bg-zinc-900 border border-violet-200 dark:border-violet-500/30 flex items-center justify-center text-4xl font-bold text-violet-900 dark:text-white mb-6 shadow-lg shadow-violet-500/10 dark:shadow-violet-900/20">
                  {t(`phases.${phaseId}.number`)}
               </div>
               <h3 className="text-xl font-bold mb-3 text-zinc-900 dark:text-white">{t(`phases.${phaseId}.title`)}</h3>
               <p className="text-sm text-zinc-600 dark:text-neutral-400 mb-4 px-4">
                  {t(`phases.${phaseId}.description`)}
               </p>
               <div className="p-3 bg-zinc-100 dark:bg-white/5 rounded-lg border border-zinc-200 dark:border-white/5 text-xs text-zinc-600 dark:text-neutral-300 w-full max-w-xs">
                  <span className="block font-semibold text-violet-600 dark:text-violet-300 mb-1">{t(`phases.${phaseId}.deliverableLabel`)}</span>
                  {t(`phases.${phaseId}.deliverable`)}
               </div>
             </motion.div>
           ))}
        </div>

        <div className="mt-16 text-center">
           <Link
             href="#agendar"
             className="px-8 py-3 rounded-full bg-violet-600 hover:bg-violet-500 text-white font-semibold transition-colors shadow-lg shadow-violet-500/20 dark:shadow-violet-900/20"
           >
             {t('cta')}
           </Link>
        </div>
      </div>
    </section>
  );
}
