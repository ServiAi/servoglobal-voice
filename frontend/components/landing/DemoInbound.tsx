'use client';

import { Turnstile } from '@marsidev/react-turnstile';

import React from 'react';
import Image from 'next/image';
import { useUltravox } from '@/hooks/useUltravox';
import { Phone, Mic, PhoneOff, User, Loader2, ChevronDown } from 'lucide-react';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import Link from 'next/link';
import { useTranslations } from 'next-intl';

const COUNTRY_CODES = [
  { code: '+1', flag: '/flags/us.svg', name: 'USA' },
  { code: '+57', flag: '/flags/co.svg', name: 'COL' },
  { code: '+52', flag: '/flags/mx.svg', name: 'MEX' },
  { code: '+34', flag: '/flags/es.svg', name: 'ESP' },
  { code: '+54', flag: '/flags/ar.svg', name: 'ARG' },
  { code: '+56', flag: '/flags/cl.svg', name: 'CHL' },
  { code: '+51', flag: '/flags/pe.svg', name: 'PER' },
];

export function DemoInbound() {
  const t = useTranslations('demoInbound');
  const tCommon = useTranslations('demoCommon');
  // Use the new Ultravox hook instead of the simulation
  const { demoState, volumeLevels, startCall, endCall, resetDemo } = useUltravox();
  // Timer logic
  const [duration, setDuration] = React.useState(0);
  const [formData, setFormData] = React.useState({
    name: '',
    email: '',
    phone: '',
    countryCode: '+57',
    company: '',
    industry: '',
    useCase: '',
    volume: '',
    painPoint: ''
  });
  const [isDropdownOpen, setIsDropdownOpen] = React.useState(false);
  const [token, setToken] = React.useState<string | null>(null);
  const dropdownRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  const handleStartCall = () => {
    if (!formData.name || !formData.email || !formData.phone || !token) return;
    
    const industryTranslated = formData.industry ? tCommon(`options.industry.${formData.industry}`) : '';
    const useCaseTranslated = formData.useCase ? tCommon(`options.useCase.${formData.useCase}`) : '';
    const volumeTranslated = formData.volume ? tCommon(`options.volume.${formData.volume}`) : '';
    const painPointTranslated = formData.painPoint ? tCommon(`options.painPoint.${formData.painPoint}`) : '';

    startCall({
      user_name: formData.name,
      user_email: formData.email,
      user_phone: `${formData.countryCode}${formData.phone}`,
      user_company: formData.company,
      user_industry: industryTranslated,
      user_use_case: useCaseTranslated,
      user_volume: volumeTranslated,
      user_pain_point: painPointTranslated
    }, token);
  };

  React.useEffect(() => {
    let interval: NodeJS.Timeout;
    
    if (demoState === 'connected') {
      interval = setInterval(() => {
        setDuration(prev => prev + 1);
      }, 1000);
    } else {
      setDuration(0);
    }

    return () => clearInterval(interval);
  }, [demoState]);

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  if (demoState === 'ended') {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center bg-zinc-50 dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-white/5">
        <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-2">{t('callEnded')}</h3>
        <p className="text-zinc-600 dark:text-zinc-400 mb-6 max-w-sm">{t('callEndedDesc')}</p>
        <div className="flex flex-col gap-3 w-full max-w-xs">
          <Link
            href="#agendar"
            onClick={resetDemo}
            className="w-full py-3 bg-violet-600 hover:bg-violet-500 text-white rounded-lg font-semibold transition-colors"
          >
            {t('scheduleConsultation')}
          </Link>
          <button
            onClick={resetDemo}
            className="w-full py-3 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-transparent hover:bg-zinc-100 dark:hover:bg-zinc-700 text-zinc-900 dark:text-white rounded-lg font-medium transition-colors"
          >
            {t('tryAgain')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="relative min-h-[500px] h-auto w-full bg-white dark:bg-zinc-950 rounded-2xl border border-zinc-200 dark:border-white/10 shadow-2xl flex flex-col transition-colors duration-300">
      {/* Background Wrapper to clip decorative elements without clipping dropdowns */}
      <div className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none">
          {/* Background Gradients */}
          <div className="absolute inset-0 bg-gradient-to-b from-blue-500/5 to-violet-500/5" />
      </div>

      {/* status bar */}
      <div className="absolute top-4 left-0 right-0 py-2 px-4 flex justify-between items-center text-xs text-zinc-500 dark:text-white/30 z-10">
        <span>{t('simulatorVersion')}</span>
        <div className="flex gap-1">
           <div className={cn("size-2 rounded-full", demoState === 'connected' ? "bg-green-500" : "bg-zinc-500")}></div>
           <span>{demoState === 'connected' ? t('online') : 'Offline'}</span>
        </div>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center relative p-6 z-10">

        {demoState === 'idle' && (
          <div className="w-full max-w-sm flex flex-col gap-4 z-10 px-4 py-6">
            <div className="text-center space-y-1 shrink-0">
              <h3 className="text-xl font-semibold text-zinc-900 dark:text-white">{t('webCall')}</h3>
              <p className="text-xs text-zinc-500">{t('selectAgentDesc')}</p>
            </div>

            <div className="space-y-2">
              {/* Contact Info */}
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder={tCommon('fields.name')}
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs"
                />
                 <input
                  type="text"
                  placeholder={tCommon('fields.company')}
                  value={formData.company}
                  onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs"
                />
                <input
                  type="email"
                  placeholder={t('emailPlaceholder')}
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs"
                />
                <div className="flex gap-2 relative">
                  {/* Custom Country Dropdown */}
                  <div className="relative" ref={dropdownRef}>
                    <button
                      type="button"
                      onClick={() => setIsDropdownOpen(!isDropdownOpen)}
                      className="h-[38px] px-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs flex items-center gap-1 min-w-[70px]"
                    >
                      {(() => {
                        const selected = COUNTRY_CODES.find(c => c.code === formData.countryCode) || COUNTRY_CODES[0];
                        return (
                          <>
                            <div className="relative w-6 h-4 overflow-hidden rounded-sm shadow-sm shrink-0">
                                <Image 
                                    src={selected.flag} 
                                    alt={selected.name} 
                                    fill 
                                    className="object-cover"
                                />
                            </div>
                            <span>{selected.code}</span>
                            <ChevronDown className="size-3 opacity-50 ml-auto" />
                          </>
                        );
                      })()}
                    </button>

                    {isDropdownOpen && (
                      <div className="absolute top-full left-0 mt-1 w-48 max-h-60 overflow-y-auto bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg shadow-xl z-50 py-1">
                        {COUNTRY_CODES.map((country) => (
                          <button
                            key={country.code}
                            type="button"
                            onClick={() => {
                              setFormData({ ...formData, countryCode: country.code });
                              setIsDropdownOpen(false);
                            }}
                            className="w-full px-4 py-2 text-left text-sm hover:bg-zinc-100 dark:hover:bg-zinc-800 flex items-center gap-3"
                          >
                             <div className="relative w-6 h-4 overflow-hidden rounded-sm shadow-sm shrink-0">
                                <Image 
                                    src={country.flag} 
                                    alt={country.name} 
                                    fill 
                                    className="object-cover"
                                />
                            </div>
                            <span className="font-medium">{country.code}</span>
                            <span className="text-zinc-500 text-xs ml-auto">{country.name}</span>
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  <input
                    type="tel"
                    placeholder={tCommon('fields.phone')}
                    value={formData.phone}
                    onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                    className="flex-1 px-3 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs h-[38px]"
                  />
                </div>
              </div>

               {/* New Fields: Industry, Use Case, Volume, Pain Point */}
               <div className="grid grid-cols-2 gap-3">
                    <select
                        value={formData.industry}
                        onChange={(e) => setFormData({ ...formData, industry: e.target.value })}
                        className="w-full px-2 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-[10px] appearance-none"
                    >
                        <option value="" disabled>{tCommon('fields.industry')}</option>
                        <option value="health">{tCommon('options.industry.health')}</option>
                        <option value="realEstate">{tCommon('options.industry.realEstate')}</option>
                        <option value="automotive">{tCommon('options.industry.automotive')}</option>
                        <option value="financial">{tCommon('options.industry.financial')}</option>
                        <option value="education">{tCommon('options.industry.education')}</option>
                        <option value="logistics">{tCommon('options.industry.logistics')}</option>
                        <option value="tourism">{tCommon('options.industry.tourism')}</option>
                        <option value="legal">{tCommon('options.industry.legal')}</option>
                        <option value="government">{tCommon('options.industry.government')}</option>
                        <option value="other">{tCommon('options.industry.other')}</option>
                    </select>

                     <select
                        value={formData.useCase}
                        onChange={(e) => setFormData({ ...formData, useCase: e.target.value })}
                        className="w-full px-2 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-[10px] appearance-none"
                    >
                        <option value="" disabled>{tCommon('fields.useCase')}</option>
                         <option value="customerService">{tCommon('options.useCase.customerService')}</option>
                        <option value="support">{tCommon('options.useCase.support')}</option>
                        <option value="collections">{tCommon('options.useCase.collections')}</option>
                        <option value="sales">{tCommon('options.useCase.sales')}</option>
                        <option value="recruitment">{tCommon('options.useCase.recruitment')}</option>
                        <option value="booking">{tCommon('options.useCase.booking')}</option>
                        <option value="ecommerce">{tCommon('options.useCase.ecommerce')}</option>
                        <option value="other">{tCommon('options.useCase.other')}</option>
                    </select>
               </div>
               
               <select
                    value={formData.volume}
                    onChange={(e) => setFormData({ ...formData, volume: e.target.value })}
                    className="w-full px-3 py-2.5 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-xs appearance-none"
                >
                    <option value="" disabled>{tCommon('fields.volume')}</option>
                    <option value="tier1">{tCommon('options.volume.tier1')}</option>
                    <option value="tier2">{tCommon('options.volume.tier2')}</option>
                    <option value="tier3">{tCommon('options.volume.tier3')}</option>
                    <option value="tier4">{tCommon('options.volume.tier4')}</option>
                </select>

                <select
                    value={formData.painPoint}
                    onChange={(e) => setFormData({ ...formData, painPoint: e.target.value })}
                    className="w-full px-2 py-2 rounded-lg bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 focus:ring-2 focus:ring-violet-500 outline-none transition-all text-[10px] appearance-none"
                >
                    <option value="" disabled>{tCommon('fields.painPoint')}</option>
                     <option value="lostCalls">{tCommon('options.painPoint.lostCalls')}</option>
                    <option value="repetitiveTasks">{tCommon('options.painPoint.repetitiveTasks')}</option>
                    <option value="highCost">{tCommon('options.painPoint.highCost')}</option>
                    <option value="slowResponse">{tCommon('options.painPoint.slowResponse')}</option>
                    <option value="qualityControl">{tCommon('options.painPoint.qualityControl')}</option>
                </select>

              <div className="flex justify-center my-2 w-full min-h-[65px]">
                  <Turnstile 
                      siteKey={process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY || '1x00000000000000000000AA'} 
                      onSuccess={setToken}
                      options={{ theme: 'auto' }}
                  />
              </div>

              <button
                onClick={handleStartCall}
                disabled={!formData.name || !formData.email || !formData.phone || !formData.company || !formData.industry || !formData.useCase || !formData.volume || !formData.painPoint || !token}
                className="w-full py-2.5 bg-zinc-900 dark:bg-white text-white dark:text-black font-bold rounded-lg hover:bg-zinc-800 dark:hover:bg-zinc-200 transition-all active:scale-[0.98] shadow-xl shadow-black/5 dark:shadow-white/5 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed text-xs"
              >
                <Phone className="size-4" />
                {t('callNow')}
              </button>
              {(!formData.name || !formData.email || !formData.phone || !formData.company || !formData.industry || !formData.useCase || !formData.volume || !formData.painPoint) && (
                  <p className="text-[10px] text-amber-600 dark:text-amber-500 text-center animate-pulse">
                      {tCommon('fillAllFields')}
                  </p>
              )}
               <p className="text-[10px] text-zinc-400 text-center">
                  * Powered by ServiGlobal AI Voice Engine
               </p>
            </div>
          </div>
        )}

        {(demoState === 'connecting' || demoState === 'connected') && (
          <div className="flex flex-col items-center z-10 w-full">
            <div className="mb-8 relative">
              <div className={cn(
                "w-32 h-32 rounded-full flex items-center justify-center transition-all duration-500",
                demoState === 'connected' ? "bg-violet-500/20 animate-pulse-ring" : "bg-zinc-100 dark:bg-zinc-800"
              )}>
                <User className="size-12 text-zinc-400 dark:text-white/80" />
              </div>
              {demoState === 'connecting' && (
                  <div className="absolute inset-0 flex items-center justify-center">
                      <Loader2 className="size-16 text-violet-600 dark:text-violet-400 animate-spin opacity-50 absolute" />
                  </div>
              )}
            </div>

            <h3 className="text-2xl font-bold text-zinc-900 dark:text-white mb-1">
              {demoState === 'connecting' ? t('connecting') : `${t('agent')} ${t('agentSales')}`}
            </h3>
            <p className="text-zinc-500 dark:text-zinc-400 mb-8 font-mono">{formatDuration(duration)}</p>

            {/* Visualizer */}
            <div className="h-16 flex items-center gap-1 mb-12">
               {demoState === 'connected' ? (
                 volumeLevels.map((level: number, i: number) => (
                    <motion.div
                      key={i}
                      initial={{ height: 10 }}
                      animate={{ height: level }}
                      transition={{ type: "spring", stiffness: 300, damping: 20 }}
                      className="w-3 bg-gradient-to-t from-violet-600 to-blue-400 rounded-full"
                    />
                 ))
               ) : (
                  <div className="text-zinc-600 text-sm animate-pulse">{t('establishingConnection')}</div>
               )}
            </div>

            <button
              onClick={endCall}
              className="size-16 rounded-full bg-red-500 hover:bg-red-600 flex items-center justify-center text-white shadow-lg transition-transform hover:scale-110 active:scale-95"
            >
              <PhoneOff className="size-8" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
