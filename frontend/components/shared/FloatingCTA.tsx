'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Calendar, Phone, X } from 'lucide-react';
import { getCalApi } from "@calcom/embed-react";
import { DemoInbound } from '@/components/landing/DemoInbound';
import { DemoOutbound } from '@/components/landing/DemoOutbound';
import { cn } from '@/lib/utils';
import { useTranslations } from 'next-intl';

export function FloatingCTA() {
  const t = useTranslations('floatingCta');
  const tDemo = useTranslations('voiceDemo');
  const [isDemoOpen, setIsDemoOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<'inbound' | 'outbound'>('inbound');

  // Initialize Cal.com
  useEffect(() => {
    (async function () {
      const cal = await getCalApi({"namespace":"agendamiento-de-citas-serviglobal-ai"});
      cal("ui", {"hideEventTypeDetails":false,"layout":"month_view"});
    })();
  }, []);

  return (
    <>
      {/* Floating Buttons */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-4">
        {/* Demo Button */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1 }}
          className="relative"
        >
          {/* Pulsing ring */}
          <span className="absolute inset-0 rounded-full bg-zinc-500 dark:bg-white animate-ping opacity-30" />
          <span className="absolute inset-0 rounded-full bg-zinc-400 dark:bg-white/50 animate-pulse opacity-20" />
          <button
            suppressHydrationWarning
            onClick={() => setIsDemoOpen(true)}
            className="relative size-14 rounded-full bg-zinc-900 dark:bg-white text-white dark:text-black shadow-xl shadow-black/30 dark:shadow-white/20 flex items-center justify-center hover:scale-110 transition-transform z-10"
            title={t('demoButton')}
          >
            <Phone className="size-6" />
          </button>
        </motion.div>

        {/* Schedule Button (Cal.com) */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1.2 }}
          className="relative"
        >
          {/* Pulsing glow rings */}
          <span className="absolute inset-0 rounded-full bg-gradient-to-r from-violet-500 to-fuchsia-500 animate-ping opacity-40" />
          <span className="absolute -inset-1 rounded-full bg-gradient-to-r from-violet-600 to-fuchsia-600 animate-pulse opacity-30 blur-sm" />
          <button
            suppressHydrationWarning
            data-cal-namespace="agendamiento-de-citas-serviglobal-ai"
            data-cal-link="jeysson-aly-contreras-asxwla/agendamiento-de-citas-serviglobal-ai"
            data-cal-config='{"layout":"month_view"}'
            className="relative size-14 rounded-full bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white shadow-xl shadow-violet-500/40 flex items-center justify-center hover:scale-110 transition-transform z-10"
            title={t('scheduleButton')}
          >
            <Calendar className="size-6" />
          </button>
        </motion.div>
      </div>

      {/* Demo Modal */}
      <AnimatePresence>
        {isDemoOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[100] bg-black/60 backdrop-blur-sm flex items-center justify-center p-4"
            onClick={() => setIsDemoOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.9, y: 20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.9, y: 20 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              onClick={(e) => e.stopPropagation()}
              className="bg-white dark:bg-zinc-900 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden shadow-2xl border border-zinc-200 dark:border-white/10"
            >
              {/* Modal Header */}
              <div className="flex items-center justify-between p-4 border-b border-zinc-200 dark:border-white/10">
                <h3 className="text-lg font-bold text-zinc-900 dark:text-white">
                  {tDemo('title')}
                </h3>
                <button
                  onClick={() => setIsDemoOpen(false)}
                  className="size-10 rounded-full hover:bg-zinc-100 dark:hover:bg-white/10 flex items-center justify-center transition-colors"
                >
                  <X className="size-5 text-zinc-500" />
                </button>
              </div>

              {/* Tabs */}
              <div className="flex justify-center p-4 border-b border-zinc-100 dark:border-white/5">
                <div className="flex p-1 bg-zinc-100 dark:bg-zinc-800 rounded-xl">
                  <button
                    onClick={() => setActiveTab('inbound')}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-semibold transition-all",
                      activeTab === 'inbound'
                        ? "bg-white dark:bg-zinc-700 text-zinc-900 dark:text-white shadow-sm"
                        : "text-zinc-500 dark:text-zinc-400"
                    )}
                  >
                    {tDemo('inboundTab')}
                  </button>
                  <button
                    onClick={() => setActiveTab('outbound')}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-semibold transition-all",
                      activeTab === 'outbound'
                        ? "bg-green-500 text-white shadow-sm"
                        : "text-zinc-500 dark:text-zinc-400"
                    )}
                  >
                    {tDemo('outboundTab')}
                  </button>
                </div>
              </div>

              {/* Demo Content */}
              <div className="p-4 overflow-y-auto max-h-[60vh]">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeTab}
                    initial={{ opacity: 0, x: activeTab === 'inbound' ? -20 : 20 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0, x: activeTab === 'inbound' ? 20 : -20 }}
                    transition={{ duration: 0.2 }}
                  >
                    {activeTab === 'inbound' ? <DemoInbound /> : <DemoOutbound />}
                  </motion.div>
                </AnimatePresence>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
