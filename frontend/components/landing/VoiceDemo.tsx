'use client';

import React, { useState } from 'react';
import { DemoInbound } from './DemoInbound';
import { DemoOutbound } from './DemoOutbound';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { useTranslations } from 'next-intl';

export function VoiceDemo() {
  const t = useTranslations('voiceDemo');
  const [activeTab, setActiveTab] = useState<'inbound' | 'outbound'>('inbound');

  return (
    <section id="demos" className="py-24 bg-zinc-50 dark:bg-black relative overflow-hidden transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <div className="text-center max-w-3xl mx-auto mb-10">
            <h2 className="text-3xl md:text-5xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-violet-600 to-zinc-600 dark:from-white dark:to-neutral-500 mb-6">
                {t('title')}
            </h2>
            <p className="text-lg text-zinc-600 dark:text-neutral-400">
                {t('subtitle')}
                <br />
                <span className="text-sm text-zinc-500 dark:text-neutral-500">{t('disclaimer')}</span>
            </p>
        </div>

        <div className="grid gap-4 md:grid-cols-2 max-w-4xl mx-auto mb-10">
          <div className="rounded-2xl border border-zinc-200 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-neutral-900/60">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-violet-600 dark:text-violet-400">
              {t('exploreLabel')}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-neutral-400">
              {t('exploreText')}
            </p>
          </div>
          <div className="rounded-2xl border border-zinc-200 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-neutral-900/60">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-green-600 dark:text-green-400">
              {t('commercialLabel')}
            </p>
            <p className="mt-2 text-sm leading-relaxed text-zinc-600 dark:text-neutral-400">
              {t('commercialText')}
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex flex-col items-center gap-4 mb-12">
            <div className="grid w-full max-w-2xl grid-cols-1 sm:grid-cols-2 p-1 bg-white dark:bg-neutral-900/50 border border-zinc-200 dark:border-white/10 rounded-xl backdrop-blur-sm shadow-sm dark:shadow-none">
                <button
                    suppressHydrationWarning
                    onClick={() => setActiveTab('inbound')}
                    className={cn(
                        "px-6 py-3 rounded-lg text-sm font-semibold transition-all duration-300",
                        activeTab === 'inbound' 
                            ? "bg-zinc-900 text-white dark:bg-white dark:text-black shadow-lg" 
                            : "text-zinc-500 dark:text-neutral-400 hover:text-black dark:hover:text-white"
                    )}
                >
                    {t('inboundTab')}
                </button>
                <button
                    suppressHydrationWarning
                    onClick={() => setActiveTab('outbound')}
                    className={cn(
                        "px-6 py-3 rounded-lg text-sm font-semibold transition-all duration-300",
                        activeTab === 'outbound' 
                            ? "bg-green-500 text-white shadow-lg shadow-green-900/20" 
                            : "text-zinc-500 dark:text-neutral-400 hover:text-black dark:hover:text-white"
                    )}
                >
                    {t('outboundTab')}
                </button>
            </div>
            <p className="max-w-2xl text-center text-sm text-zinc-500 dark:text-neutral-500">
              {activeTab === 'inbound' ? t('inboundHint') : t('outboundHint')}
            </p>
        </div>

        {/* Demo Stage */}
        <div className="max-w-4xl mx-auto">
             <motion.div
                key={activeTab}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4 }}
                className="bg-white dark:bg-neutral-900 rounded-3xl p-1 md:p-2 border border-zinc-200 dark:border-white/5 shadow-2xl shadow-violet-500/5"
             >
                 {activeTab === 'inbound' ? <DemoInbound /> : <DemoOutbound />}
             </motion.div>
        </div>
      </div>
    </section>
  );
}

