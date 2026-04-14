import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import '../globals.css';
import { cn } from '@/lib/utils';
import { Footer } from '@/components/shared/Footer';
import { NextIntlClientProvider } from 'next-intl';
import { getMessages } from 'next-intl/server';
import { locales } from '@/i18n';
import { ThemeProvider } from '@/components/providers/ThemeProvider';
import { JsonLd } from '@/components/shared/JsonLd';

const inter = Inter({ subsets: ['latin'] });

type Props = {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
};

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { locale } = await params;
  const messages = await getMessages();
  const t = messages.metadata as {
    title: string;
    description: string;
    keywords: string;
    ogTitle: string;
    ogDescription: string;
    twitterTitle: string;
    twitterDescription: string;
  };
  
  return {
    title: t.title,
    description: t.description,
    keywords: t.keywords,
    openGraph: {
      title: t.ogTitle,
      description: t.ogDescription,
      url: `https://www.serviglobal-ia.com/${locale}`,
      siteName: 'ServiGlobal · IA',
      locale: locale,
      type: 'website',
    },
    twitter: {
      card: 'summary_large_image',
      title: t.twitterTitle,
      description: t.twitterDescription,
    },
    alternates: {
      canonical: `https://www.serviglobal-ia.com/${locale}`,
      languages: {
        'es': 'https://www.serviglobal-ia.com/es',
        'en': 'https://www.serviglobal-ia.com/en',
      },
    },
    robots: {
      index: true,
      follow: true,
    },
    verification: {
      google: 'RyDrOMFBi4qFU_P6L7F1p3jTyvWLmdH236qnQILKRR8',
    },
  };
}

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;
  const messages = await getMessages();

  return (
    <html lang={locale} className="scroll-smooth" suppressHydrationWarning>
      <body className={cn(inter.className, "antialiased min-h-screen selection:bg-violet-500/30 selection:text-violet-900 dark:selection:text-white transition-colors duration-300")}>
        <NextIntlClientProvider messages={messages}>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            disableTransitionOnChange
          >
            <JsonLd />
            {children}
            <Footer />
          </ThemeProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}


