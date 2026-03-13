'use client';

import React from 'react';
import { getCalApi } from "@calcom/embed-react";
import { useEffect } from "react";
import { Calendar } from 'lucide-react';
import { useTranslations } from 'next-intl';

export function Booking() {
  const t = useTranslations('booking');
  
  useEffect(() => {
    (async function () {
      const cal = await getCalApi({"namespace":"serviglobal-ventas-ia"});
      cal("ui", {"hideEventTypeDetails":false,"layout":"month_view"});
    })();
  }, []);

  return (
    <section id="agendar" className="py-24 bg-white dark:bg-black relative transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6">
        <div className="text-center max-w-3xl mx-auto mb-12">
           <h2 className="text-3xl md:text-5xl font-bold text-zinc-900 dark:text-white mb-6">
             {t('title')}
           </h2>
           <p className="text-lg text-zinc-600 dark:text-neutral-400 mb-8">
             {t('description')}
           </p>
        </div>

        <div className="flex justify-center">
          <button 
            suppressHydrationWarning
            data-cal-namespace="serviglobal-ventas-ia"
            data-cal-link="serviglobal/serviglobal-ventas-ia"
            data-cal-config='{"layout":"month_view","useSlotsViewOnSmallScreen":"true"}'
            className="inline-flex items-center gap-3 px-10 py-5 bg-gradient-to-r from-violet-600 to-fuchsia-600 text-white rounded-full font-bold text-lg hover:from-violet-700 hover:to-fuchsia-700 transition-all hover:scale-105 active:scale-95 shadow-xl shadow-violet-500/30"
          >
            <Calendar className="size-6" />
            {t('cta')}
          </button>
        </div>
      </div>
    </section>
  );
}
