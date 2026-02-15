'use client';

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

  return (
    <section id="integraciones" className="py-24 bg-white dark:bg-black border-t border-zinc-200 dark:border-white/5 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <div className="flex flex-col md:flex-row gap-16 items-center">
          
          <div className="md:w-1/3">
             <h2 className="text-3xl font-bold text-zinc-900 dark:text-white mb-6 text-left">
               {t('title')} <span className="text-violet-600 dark:text-violet-500">{t('titleHighlight')}</span>.
             </h2>
             <p className="text-zinc-600 dark:text-neutral-400 mb-4 leading-relaxed">
               {t('description')}
             </p>
             <p className="text-sm text-violet-600 dark:text-violet-400 leading-relaxed font-medium">
               {t('description2')}
             </p>
          </div>

          <div className="md:w-2/3 grid sm:grid-cols-2 gap-6 w-full">
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
          </div>

        </div>
      </div>
    </section>
  );
}
