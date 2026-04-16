'use client';

import { motion } from 'framer-motion';
import { Phone, Plug, Users } from 'lucide-react';
import { useTranslations } from 'next-intl';

const TRUST_ITEMS = [
  { key: 'voice', icon: Phone },
  { key: 'infrastructure', icon: Plug },
  { key: 'implementation', icon: Users },
] as const;

export function TrustStrip() {
  const t = useTranslations('trustStrip');

  return (
    <section className="bg-white dark:bg-black border-y border-zinc-200 dark:border-white/10 transition-colors duration-300">
      <div className="container mx-auto px-4 md:px-6 py-6">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="grid gap-4 md:grid-cols-3"
        >
          {TRUST_ITEMS.map(({ key, icon: Icon }) => (
            <div
              key={key}
              className="flex items-start gap-3 rounded-xl border border-zinc-200 dark:border-white/10 bg-zinc-50 dark:bg-zinc-950 px-4 py-4"
            >
              <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-lg bg-violet-100 dark:bg-violet-950/40">
                <Icon className="size-5 text-violet-700 dark:text-violet-300" />
              </div>
              <div>
                <p className="text-sm font-bold text-zinc-900 dark:text-white">
                  {t(`items.${key}.title`)}
                </p>
                <p className="mt-1 text-xs leading-relaxed text-zinc-600 dark:text-neutral-400">
                  {t(`items.${key}.description`)}
                </p>
              </div>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
