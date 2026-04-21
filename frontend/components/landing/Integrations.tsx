'use client';

import { motion, useScroll, useTransform } from 'framer-motion';
import { useRef } from 'react';
import { useTranslations } from 'next-intl';

const INTEGRATIONS = {
  "channels": ["Telefonía / VoIP", "Mensajería", "Web Chat"],
  "agenda": ["Calendarios", "Email", "Notificaciones"],
  "crm": ["CRM / Helpdesk", "Sistemas de tickets", "Herramientas internas"],
  "infrastructure": ["PBX", "SIP Trunks", "Sistemas internos", "APIs"]
};

const CATEGORY_IDS = ['channels', 'agenda', 'crm', 'infrastructure'] as const;

export function Integrations() {
  const t = useTranslations('integrations');
  const containerRef = useRef<HTMLElement>(null);

  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start end", "end start"]
  });

  const yLeft = useTransform(scrollYProgress, [0, 1], [-60, 60]);
  const yRight = useTransform(scrollYProgress, [0, 1], [60, -60]);
  const yBlob = useTransform(scrollYProgress, [0, 1], [-120, 120]);

  return (
    <section ref={containerRef} id="integraciones" className="relative py-24 bg-white dark:bg-black border-t border-zinc-200 dark:border-white/5 transition-colors duration-300 overflow-hidden">
      {/* Decorative Parallax Blob */}
      <motion.div style={{ y: yBlob }} className="absolute -bottom-20 -right-20 w-96 h-96 bg-fuchsia-600/5 dark:bg-fuchsia-600/10 rounded-full blur-[120px] pointer-events-none -z-10" />

      <div className="container mx-auto px-4 md:px-6 relative z-10">
        <div className="flex flex-col md:flex-row gap-16 items-center">
          
          <motion.div style={{ y: yLeft }} className="md:w-1/3">
             <h2 className="text-3xl font-bold text-zinc-900 dark:text-white mb-6 text-left">
               {t('title')} <span className="text-violet-600 dark:text-violet-500">{t('titleHighlight')}</span>.
             </h2>
             <p className="text-zinc-600 dark:text-neutral-400 mb-4 leading-relaxed">
               {t('description')}
             </p>
             <p className="text-sm text-violet-600 dark:text-violet-400 leading-relaxed font-medium">
               {t('description2')}
             </p>
          </motion.div>

          <motion.div style={{ y: yRight }} className="md:w-2/3 grid sm:grid-cols-2 gap-6 w-full">
             {CATEGORY_IDS.map((categoryId) => (
                <div key={categoryId} className="bg-zinc-50 dark:bg-zinc-900/50 border border-zinc-200 dark:border-white/10 rounded-xl p-6 hover:border-violet-500/30 transition-colors shadow-sm dark:shadow-none">
                   <h3 className="text-zinc-900 dark:text-white font-bold mb-4 border-b border-zinc-200 dark:border-white/5 pb-2">{t(`categories.${categoryId}`)}</h3>
                   <div className="flex flex-wrap gap-2">
                      {INTEGRATIONS[categoryId].map((tool) => (
                         <span key={tool} className="text-sm px-3 py-1 bg-white dark:bg-black rounded border border-zinc-200 dark:border-white/10 text-zinc-600 dark:text-neutral-300">
                           {tool}
                         </span>
                      ))}
                   </div>
                </div>
             ))}
          </motion.div>

        </div>
      </div>
    </section>
  );
}
