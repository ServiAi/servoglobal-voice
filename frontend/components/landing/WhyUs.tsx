'use client';

import { motion } from 'framer-motion';
import { useRef } from 'react';
import { Phone, Plug, Users, Sparkles, Server, HeartHandshake } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  sectionDesktop,
  useParallaxLayer,
  useSectionParallax,
} from '@/hooks/useSectionParallax';

const FEATURES = [
  { key: 'voiceExperience', icon: Phone, color: 'emerald' },
  { key: 'existingInfra', icon: Plug, color: 'blue' },
  { key: 'guidedImplementation', icon: Users, color: 'violet' },
  { key: 'clickToIACall', icon: Sparkles, color: 'amber' },
  { key: 'customVoiceInfra', icon: Server, color: 'rose' },
  { key: 'continuousSupport', icon: HeartHandshake, color: 'cyan' },
] as const;

const containerVariants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.15,
    },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.6,
      ease: [0.16, 1, 0.3, 1],
    },
  },
};

const colorMap: Record<string, { bg: string; icon: string; border: string }> = {
  emerald: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
    icon: 'text-emerald-600 dark:text-emerald-400',
    border: 'border-emerald-200 dark:border-emerald-500/20',
  },
  blue: {
    bg: 'bg-blue-100 dark:bg-blue-900/30',
    icon: 'text-blue-600 dark:text-blue-400',
    border: 'border-blue-200 dark:border-blue-500/20',
  },
  violet: {
    bg: 'bg-violet-100 dark:bg-violet-900/30',
    icon: 'text-violet-600 dark:text-violet-400',
    border: 'border-violet-200 dark:border-violet-500/20',
  },
  amber: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    icon: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-200 dark:border-amber-500/20',
  },
  rose: {
    bg: 'bg-rose-100 dark:bg-rose-900/30',
    icon: 'text-rose-600 dark:text-rose-400',
    border: 'border-rose-200 dark:border-rose-500/20',
  },
  cyan: {
    bg: 'bg-cyan-100 dark:bg-cyan-900/30',
    icon: 'text-cyan-600 dark:text-cyan-400',
    border: 'border-cyan-200 dark:border-cyan-500/20',
  },
};

export function WhyUs() {
  const t = useTranslations('whyUs');
  const containerRef = useRef<HTMLElement>(null);
  const { profile, scrollYProgress } = useSectionParallax({
    target: containerRef,
    desktopProfile: sectionDesktop,
  });
  const yHeader = useParallaxLayer(scrollYProgress, profile, 'content');
  const yBlob = useParallaxLayer(scrollYProgress, profile, 'background', -1);

  return (
    <section ref={containerRef} className="relative py-24 bg-white dark:bg-zinc-950 transition-colors duration-300 overflow-hidden">
      <motion.div
        style={{ y: yBlob }}
        className="absolute -top-20 left-1/2 h-[30rem] w-[30rem] -translate-x-1/2 rounded-full bg-violet-600/5 dark:bg-violet-600/10 blur-[120px] pointer-events-none -z-10"
      />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        {/* Header */}
        <motion.div
          style={{ y: yHeader }}
          initial={{ opacity: 0, scale: 0.98 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, margin: '-100px' }}
          transition={{ duration: 0.6 }}
          className="text-center mb-16"
        >
          <h2 className="text-4xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-4">
            {t('title')}
          </h2>
          <p className="text-lg text-zinc-600 dark:text-zinc-400 max-w-2xl mx-auto">
            {t('subtitle')}
          </p>
        </motion.div>

        {/* Grid */}
        <motion.div
          variants={containerVariants}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-50px' }}
          className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6 md:gap-8"
        >
          {FEATURES.map(({ key, icon: Icon, color }) => {
            const colors = colorMap[color];
            return (
              <motion.div
                key={key}
                variants={itemVariants}
                className={`group relative p-8 rounded-2xl border ${colors.border} bg-zinc-50 dark:bg-zinc-900/50 hover:bg-white dark:hover:bg-zinc-800/50 transition-all duration-300 hover:shadow-xl dark:hover:shadow-2xl dark:hover:shadow-black/30`}
              >
                {/* Icon */}
                <div
                  className={`size-14 rounded-xl ${colors.bg} flex items-center justify-center mb-6 group-hover:scale-110 transition-transform duration-300`}
                >
                  <Icon className={`size-7 ${colors.icon}`} />
                </div>

                {/* Title */}
                <h3 className="text-xl font-bold text-zinc-900 dark:text-white mb-2">
                  {t(`features.${key}.title`)}
                </h3>

                {/* Subtitle */}
                <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-3">
                  {t(`features.${key}.subtitle`)}
                </p>

                {/* Description */}
                <p className="text-sm text-zinc-600 dark:text-zinc-500 leading-relaxed">
                  {t(`features.${key}.description`)}
                </p>
              </motion.div>
            );
          })}
        </motion.div>
      </div>
    </section>
  );
}
