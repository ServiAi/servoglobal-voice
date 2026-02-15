'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { cn } from '@/lib/utils';
import { Globe, Menu, X, Phone } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useTranslations, useLocale } from 'next-intl';
import { ThemeToggle } from '../ui/ThemeToggle';

export function Header() {
  const t = useTranslations('header');
  const locale = useLocale();
  const pathname = usePathname();
  const router = useRouter();
  
  const [isScrolled, setIsScrolled] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const NAV_LINKS = [
    { name: t('cases'), href: '#casos' },
    { name: t('howItWorks'), href: '#como-funciona' },
    { name: t('integrations'), href: '#integraciones' },
    { name: t('pricing'), href: '#precios' },
    { name: t('demo'), href: '#demos' },
  ];

  const switchLocale = (newLocale: string) => {
    const currentPath = pathname.replace(`/${locale}`, '');
    router.push(`/${newLocale}${currentPath || ''}`);
  };

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <header
      className={cn(
        'fixed top-0 left-0 right-0 z-50 transition-all duration-300 border-b',
        isScrolled
          ? 'bg-white/80 dark:bg-black/80 backdrop-blur-md border-zinc-200/50 dark:border-white/10 py-3 shadow-sm dark:shadow-none'
          : 'bg-white/90 dark:bg-black/90 backdrop-blur-md border-zinc-200/30 dark:border-white/5 py-5'
      )}
    >
      <div className="container mx-auto px-4 md:px-6 flex items-center justify-between">
        <Link href={`/${locale}`} className="flex items-center gap-2 group">
          <div className="relative size-9 rounded-full bg-gradient-to-tr from-blue-500 to-violet-500 flex items-center justify-center overflow-hidden shadow-lg shadow-violet-500/20 group-hover:shadow-violet-500/40 transition-all">
             <Globe className="absolute size-5 text-white/40 animate-spin-slow" strokeWidth={1.5} />
             <Phone className="absolute size-4 text-white fill-white/20 z-10" strokeWidth={2.5} />
          </div>
          <span className="text-lg font-bold tracking-tight text-zinc-900 dark:text-white transition-colors flex items-center gap-1.5">
            ServiGlobal
            <span className="flex items-center justify-center size-2 rounded-[1px] bg-violet-600 dark:bg-violet-500 animate-pulse" />
            <span className="text-violet-600 dark:text-violet-500">IA</span>
          </span>
        </Link>

        {/* Desktop Nav */}
        <nav className="hidden md:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <Link
              key={link.name}
              href={link.href}
              className="text-sm font-medium text-zinc-600 dark:text-white/70 hover:text-zinc-900 dark:hover:text-white transition-colors"
            >
              {link.name}
            </Link>
          ))}
        </nav>

        {/* Desktop CTA + Language Switcher */}
        <div className="hidden md:flex items-center gap-4">
          <ThemeToggle />
          
          {/* Language Switcher */}
          <div className="flex items-center gap-1 rounded-full p-1 border bg-zinc-100 dark:bg-white/5 border-zinc-200 dark:border-white/5">
            <button
              onClick={() => switchLocale('es')}
              className={cn(
                "px-3 py-1 rounded-full text-xs font-semibold transition-all",
                locale === 'es' 
                  ? "bg-violet-600 text-white" 
                  : "text-zinc-600 dark:text-white/60 hover:text-black dark:hover:text-white"
              )}
            >
              ES
            </button>
            <button
              onClick={() => switchLocale('en')}
              className={cn(
                "px-3 py-1 rounded-full text-xs font-semibold transition-all",
                locale === 'en' 
                  ? "bg-violet-600 text-white" 
                  : "text-zinc-600 dark:text-white/60 hover:text-black dark:hover:text-white"
              )}
            >
              EN
            </button>
          </div>
          
          <Link
            href="#agendar"
            className="px-5 py-2 rounded-full font-semibold text-sm bg-black text-white dark:bg-white dark:text-black hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-colors shadow-lg"
          >
            {t('cta')}
          </Link>
        </div>

        {/* Mobile Toggle */}
        <div className="flex md:hidden items-center gap-2">
          <ThemeToggle />

          {/* Mobile Language Switcher */}
          <div className="flex items-center gap-1 rounded-full p-1 border bg-zinc-100 dark:bg-white/5 border-zinc-200 dark:border-white/5">
            <button
              onClick={() => switchLocale('es')}
              className={cn(
                "px-2 py-1 rounded-full text-xs font-semibold transition-all",
                locale === 'es' 
                  ? "bg-violet-600 text-white" 
                  : "text-zinc-600 dark:text-white/60"
              )}
            >
              ES
            </button>
            <button
              onClick={() => switchLocale('en')}
              className={cn(
                "px-2 py-1 rounded-full text-xs font-semibold transition-all",
                locale === 'en' 
                  ? "bg-violet-600 text-white" 
                  : "text-zinc-600 dark:text-white/60"
              )}
            >
              EN
            </button>
          </div>
          
          <button
            className="p-1 text-zinc-900 dark:text-white transition-colors"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          >
            {mobileMenuOpen ? <X /> : <Menu />}
          </button>
        </div>
      </div>

      {/* Mobile Menu */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-white/95 dark:bg-black/95 border-b border-zinc-200 dark:border-white/10 overflow-hidden backdrop-blur-xl"
          >
            <nav className="flex flex-col p-4 gap-4">
              {NAV_LINKS.map((link) => (
                <Link
                  key={link.name}
                  href={link.href}
                  onClick={() => setMobileMenuOpen(false)}
                  className="text-zinc-800 dark:text-white/80 hover:text-violet-600 dark:hover:text-white font-medium py-2 border-b border-zinc-100 dark:border-white/5"
                >
                  {link.name}
                </Link>
              ))}
              <Link
                href="#agendar"
                onClick={() => setMobileMenuOpen(false)}
                className="mt-2 w-full text-center px-5 py-3 rounded-xl bg-violet-600 text-white font-bold hover:bg-violet-700 transition-colors"
              >
                {t('cta')}
              </Link>
            </nav>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
