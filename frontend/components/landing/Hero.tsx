'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';
import { ArrowRight, Sparkles } from 'lucide-react';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';

const HeroFuturistic = dynamic(() => import('../hero-futuristic').then(mod => mod.HeroFuturistic), { 
  ssr: false,
  loading: () => <div className="w-full h-full min-h-[500px] bg-transparent" />
});

const AnimatedShaderBackground = dynamic(() => import('../ui/animated-shader-background'), { 
  ssr: false,
  loading: () => null
});

export function Hero() {
  const t = useTranslations('hero');
  
  return (
    <section className="relative min-h-[80vh] md:min-h-screen flex items-center bg-white dark:bg-black overflow-hidden pt-20 pb-8 md:pb-0 transition-colors duration-300">
      {/* Mobile Animated Background - Only visible on mobile */}
      <div className="md:hidden absolute inset-0 z-0 opacity-10 dark:opacity-100">
        <AnimatedShaderBackground />
      </div>
      
      {/* Desktop Background Effects */}
      <div className="hidden md:block absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--tw-gradient-stops))] from-violet-100/50 via-white to-white dark:from-violet-900/20 dark:via-black dark:to-black opacity-60 dark:opacity-40" />
      <div className="hidden md:block absolute top-1/4 right-0 w-[600px] h-[600px] bg-violet-600/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="container mx-auto px-4 md:px-6 relative z-10 grid lg:grid-cols-2 gap-12 items-center">
        
        {/* LEFT COLUMN: TEXT CONTENT */}
        <div className="flex flex-col items-center lg:items-start text-center lg:text-left">
          <motion.div
             initial={{ opacity: 0, x: -20 }}
             animate={{ opacity: 1, x: 0 }}
             transition={{ duration: 0.6 }}
             className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-violet-100 dark:bg-white/5 border border-violet-200 dark:border-white/10 text-xs font-medium text-violet-700 dark:text-violet-300 mb-8 backdrop-blur-sm"
          >
             <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-violet-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-violet-500"></span>
              </span>
             {t('badge')}
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
            className="text-[1.75rem] sm:text-4xl md:text-6xl lg:text-7xl font-bold tracking-tight text-zinc-900 dark:text-white mb-6 leading-tight"
          >
            {t('titlePart1')}{" "}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-violet-600 to-fuchsia-600 dark:from-violet-400 dark:to-fuchsia-400">
              {t('titlePart2')}
            </span>
            <br />
            {t('titlePart3')}
          </motion.h1>

          <motion.p
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.2 }}
            className="text-sm sm:text-base md:text-xl text-zinc-600 dark:text-neutral-400 mb-4 md:mb-6 max-w-xl leading-relaxed px-4 sm:px-0"
          >
            <span className="hidden sm:inline">{t('descriptionFull')}</span>
            <span className="sm:hidden">{t('descriptionShort')}</span>
          </motion.p>

          {/* Microcopy: Setup + Super Plus (Regla 2.2, 8.2, 8.3) */}
          <motion.div
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.6, delay: 0.25 }}
            className="mb-8 md:mb-10 max-w-xl px-4 sm:px-0 space-y-2"
          >
            <p className="text-xs text-zinc-500 dark:text-neutral-500 leading-relaxed">
              {t('microcopySetup')}
            </p>
            <p className="text-xs text-violet-600 dark:text-violet-400 leading-relaxed flex items-start gap-1.5">
              <Sparkles className="size-3.5 mt-0.5 shrink-0" />
              {t('microcopySuperPlus')}
            </p>
          </motion.div>

          <motion.div
             initial={{ opacity: 0, x: -20 }}
             animate={{ opacity: 1, x: 0 }}
             transition={{ duration: 0.6, delay: 0.3 }}
             className="flex flex-col sm:flex-row gap-4 w-full sm:w-auto"
          >
              <Link
                href="#agendar"
                className="px-8 py-4 rounded-full bg-black dark:bg-white text-white dark:text-black font-bold hover:bg-violet-800 dark:hover:bg-violet-50 transition-all hover:scale-105 active:scale-95 flex items-center justify-center gap-2 text-lg shadow-xl shadow-violet-500/20 dark:shadow-[0_0_20px_-5px_white] dark:shadow-white/10"
              >
                {t('ctaPrimary')}
                <ArrowRight className="size-5" />
              </Link>
              <Link
                href="#demos"
                className="px-8 py-4 rounded-full bg-violet-100 dark:bg-white/5 border border-violet-200 dark:border-white/10 text-violet-900 dark:text-white font-semibold hover:bg-violet-200 dark:hover:bg-white/10 transition-colors flex items-center justify-center gap-2 text-lg backdrop-blur-sm"
              >
                <Sparkles className="size-5 text-violet-600 dark:text-violet-400" />
                {t('ctaSecondary')}
              </Link>
          </motion.div>
        </div>

        {/* RIGHT COLUMN: HERO FUTURISTIC - Hidden on mobile, visible from md */}
        <div className="hidden md:flex relative items-center justify-center h-full">
             <motion.div
                initial={{ opacity: 0, scale: 0.8 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 1.2, delay: 0.4 }}
                className="relative w-full h-full min-h-[400px] lg:min-h-[500px]"
             >
                <HeroFuturistic />
             </motion.div>
        </div>

      </div>
    </section>
  );
}
