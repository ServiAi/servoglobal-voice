'use client';

import Link from 'next/link';
import { useTranslations } from 'next-intl';
import { ContactModal } from './ContactModal';

export function Footer() {
  const t = useTranslations('footer');

  return (
    <footer className="bg-zinc-100 dark:bg-zinc-950 border-t border-zinc-200 dark:border-white/5 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6 py-16">
        
        {/* Footer CTA (Regla 8) */}


        <div className="grid md:grid-cols-3 gap-8 mb-12">
          {/* Logo & Tagline */}
          <div>
            <h3 className="text-xl font-bold text-zinc-900 dark:text-white mb-2">
              ServiGlobal <span className="text-violet-600">·</span> IA
            </h3>
            <p className="text-sm text-zinc-500 dark:text-neutral-500">
              {t('tagline')}
            </p>
            <p className="text-xs text-zinc-400 dark:text-neutral-600 mt-2 font-medium">
              Respaldado por +25 años en voz
            </p>
          </div>

          {/* Services */}
          <div>
            <h4 className="text-sm font-bold text-zinc-900 dark:text-white uppercase tracking-wider mb-4">
              {t('services')}
            </h4>
            <ul className="space-y-2 text-sm text-zinc-600 dark:text-neutral-400">
              <li>{t('servicesItems.implementation')}</li>
              <li>{t('servicesItems.voiceConsulting')}</li>
              <li>{t('servicesItems.customDev')}</li>
            </ul>
          </div>

          {/* Quick Links */}
          <div>
            <h4 className="text-sm font-bold text-zinc-900 dark:text-white uppercase tracking-wider mb-4">
              {t('product')}
            </h4>
            <ul className="space-y-2 text-sm text-zinc-600 dark:text-neutral-400">
              <li><Link href="#casos" className="hover:text-violet-600 transition-colors">Casos</Link></li>
              <li><Link href="#precios" className="hover:text-violet-600 transition-colors">Precios</Link></li>
              <li><Link href="#demos" className="hover:text-violet-600 transition-colors">Demo</Link></li>
              <li>
                <ContactModal>
                  <button className="hover:text-violet-600 transition-colors text-left">
                    {t('contact')}
                  </button>
                </ContactModal>
              </li>
            </ul>
          </div>
        </div>

        <div className="text-center pt-8 border-t border-zinc-200 dark:border-white/10 text-xs text-zinc-500 dark:text-neutral-600">
          {t('copyright')}
        </div>
      </div>
    </footer>
  );
}
