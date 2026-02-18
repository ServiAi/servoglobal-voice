"use client"

import React from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from '@/components/ui/dialog';
import { Mail, MapPin, Phone, Globe, Facebook, Linkedin, Instagram } from 'lucide-react';
import Image from 'next/image';

interface ContactModalProps {
  children?: React.ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function ContactModal({ children, open, onOpenChange }: ContactModalProps) {

  const contactInfo = [
    {
      icon: <Mail className="size-5 text-violet-600" />,
      label: 'Correo electrónico',
      value: 'comercial@serviglobal.co',
      href: 'mailto:comercial@serviglobal.co'
    },
    {
      icon: <MapPin className="size-5 text-violet-600" />,
      label: 'Ubicación',
      value: 'Avenida el Dorado No. 68 C 61 Edificio Torre Central Davivienda Bogotá D.C',
      href: 'https://maps.google.com/?q=Avenida+el+Dorado+No.+68+C+61+Edificio+Torre+Central+Davivienda+Bogota+D.C'
    },
    {
      icon: <Phone className="size-5 text-violet-600" />,
      label: 'PBX',
      value: '(601) 4053030',
      href: 'tel:6014053030'
    },
    {
      icon: <Globe className="size-5 text-violet-600" />,
      label: 'Sitio Web',
      value: 'www.serviglobal.co',
      href: 'https://www.serviglobal.co'
    }
  ];

  const socialLinks = [
    {
      icon: <Linkedin className="size-5" />,
      label: 'LinkedIn',
      href: 'https://www.linkedin.com/company/serviglobal-s-a-s/' 
    },
    {
      icon: <Facebook className="size-5" />,
      label: 'Facebook',
      href: 'https://www.facebook.com/serviglobalsas'
    },
    {
      icon: <Instagram className="size-5" />,
      label: 'Instagram',
      href: 'https://www.instagram.com/serviglobalsas_/'
    }
  ];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {children && (
        <DialogTrigger asChild>
          {children}
        </DialogTrigger>
      )}
      <DialogContent className="sm:max-w-md bg-white dark:bg-zinc-950 border-zinc-200 dark:border-white/10">
        <DialogHeader>
          <DialogTitle className="text-xl font-bold text-center mb-4 text-zinc-900 dark:text-white">Contáctanos</DialogTitle>
          <DialogDescription className="text-center text-zinc-500 dark:text-zinc-400 mb-4">
             Estamos listos para ayudarte. Encuentra nuestros canales de contacto a continuación.
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-6">
          <div className="space-y-3">
            {contactInfo.map((item, index) => (
              <a 
                key={index} 
                href={item.href}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-start gap-4 p-3 rounded-lg hover:bg-zinc-100 dark:hover:bg-zinc-900 transition-colors group border border-transparent hover:border-zinc-200 dark:hover:border-zinc-800"
              >
                <div className="shrink-0 mt-0.5 group-hover:scale-110 transition-transform bg-violet-50 dark:bg-violet-900/20 p-2 rounded-md">
                  {item.icon}
                </div>
                <div>
                  <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-0.5">{item.label}</p>
                  <p className="text-sm font-semibold text-zinc-900 dark:text-zinc-100 leading-snug">{item.value}</p>
                </div>
              </a>
            ))}
          </div>

          <a 
            href="https://wa.me/573001234567" 
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center justify-center gap-2 w-full py-3 bg-[#25D366] hover:bg-[#20bd5a] text-white rounded-lg font-bold transition-all shadow-lg shadow-green-500/20 active:scale-[0.98]"
          >
             <Phone className="size-5 fill-white" />
             Chatear en WhatsApp
          </a>

          <div className="pt-4 border-t border-zinc-200 dark:border-zinc-800">
            <p className="text-center text-xs text-zinc-500 mb-3">Síguenos en redes sociales</p>
            <div className="flex justify-center gap-4">
              {socialLinks.map((social, index) => (
                 <a
                  key={index}
                  href={social.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-3 rounded-full bg-zinc-100 dark:bg-zinc-900 text-zinc-600 dark:text-zinc-400 hover:bg-violet-100 dark:hover:bg-violet-900/20 hover:text-violet-600 dark:hover:text-violet-400 transition-all hover:scale-110"
                  title={social.label}
                 >
                   {social.icon}
                 </a>
              ))}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
