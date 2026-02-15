'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

const FAQ_KEYS = [
  'replaceTeam',
  'changeOperation',
  'voiceInfra',
  'howLong',
  'omnichannel',
  'handoffRequired',
  'ownMetrics',
  'whatIsClickToIA',
  'whatIsCallback',
  'dataPrivacy',
] as const;

export function FAQ() {
  const t = useTranslations('faq');
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  const toggle = (index: number) => {
    setOpenIndex(openIndex === index ? null : index);
  };

  return (
    <section className="py-24 bg-zinc-50 dark:bg-zinc-950 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center max-w-3xl mx-auto mb-16"
        >
          <h2 className="text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-4">
            {t('title')}
          </h2>
          <p className="text-lg text-zinc-600 dark:text-neutral-400">
            {t('subtitle')}
          </p>
        </motion.div>

        <div className="max-w-3xl mx-auto space-y-3">
          {FAQ_KEYS.map((key, index) => {
            const isOpen = openIndex === index;
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 10 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.05 }}
              >
                <button
                  onClick={() => toggle(index)}
                  className={cn(
                    'w-full text-left p-5 rounded-xl border transition-all duration-200',
                    isOpen
                      ? 'bg-white dark:bg-zinc-900 border-violet-300 dark:border-violet-500/30 shadow-lg'
                      : 'bg-white dark:bg-zinc-900/50 border-zinc-200 dark:border-white/5 hover:border-violet-200 dark:hover:border-violet-500/20'
                  )}
                >
                  <div className="flex items-center justify-between gap-4">
                    <span className="font-semibold text-zinc-900 dark:text-white text-sm md:text-base">
                      {t(`items.${key}.question`)}
                    </span>
                    <ChevronDown
                      className={cn(
                        'size-5 text-zinc-400 dark:text-neutral-500 shrink-0 transition-transform duration-200',
                        isOpen && 'rotate-180 text-violet-500'
                      )}
                    />
                  </div>
                  <AnimatePresence>
                    {isOpen && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                      >
                        <p className="mt-3 pt-3 border-t border-zinc-100 dark:border-white/5 text-sm text-zinc-600 dark:text-neutral-400 leading-relaxed">
                          {t(`items.${key}.answer`)}
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </button>
              </motion.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
