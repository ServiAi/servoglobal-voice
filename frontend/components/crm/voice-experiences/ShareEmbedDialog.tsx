'use client';

import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  buildEmbedSnippet,
  type EmbedCodeFormat,
  type EmbedMode,
  type FloatingPosition,
} from '@/lib/voice-experiences/build-embed-snippet';

type Props = {
  trigger: React.ReactNode;
  publicPath: string;
  embedPath: string;
};

type Tab = 'link' | EmbedMode;

function toAbsoluteUrl(path: string): string {
  if (typeof window === 'undefined') return path;
  return new URL(path, window.location.origin).toString();
}

export function ShareEmbedDialog({ trigger, publicPath, embedPath }: Props) {
  const t = useTranslations('crm.voiceExperiences.share');
  const [activeTab, setActiveTab] = useState<Tab>('link');
  const [format, setFormat] = useState<EmbedCodeFormat>('html');
  const [floatingText, setFloatingText] = useState(t('floating.defaultText'));
  const [floatingPosition, setFloatingPosition] = useState<FloatingPosition>('bottom-right');
  const [modalSelector, setModalSelector] = useState('');
  const [linkCopied, setLinkCopied] = useState(false);
  const [codeCopied, setCodeCopied] = useState(false);

  const publicUrl = toAbsoluteUrl(publicPath);
  const embedUrl = toAbsoluteUrl(embedPath);
  const sdkUrl = toAbsoluteUrl('/voice-embed.v1.js');

  const tabs: Tab[] = ['link', 'inline', 'floating', 'modal'];

  const copy = async (text: string, onDone: (value: boolean) => void) => {
    try {
      await navigator.clipboard.writeText(text);
      onDone(true);
      setTimeout(() => onDone(false), 2000);
    } catch {
      // Clipboard access can be denied by the browser; the user can still select and copy manually.
    }
  };

  const snippet =
    activeTab === 'link'
      ? ''
      : buildEmbedSnippet({
          mode: activeTab,
          format,
          embedUrl,
          sdkUrl,
          floatingText,
          floatingPosition,
          modalSelector: modalSelector || undefined,
        });

  return (
    <Dialog onOpenChange={() => { setLinkCopied(false); setCodeCopied(false); }}>
      <DialogTrigger asChild>{trigger}</DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('title')}</DialogTitle>
          <DialogDescription>{t('description')}</DialogDescription>
        </DialogHeader>

        <div role="tablist" aria-label={t('title')} className="flex flex-wrap gap-1.5">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              role="tab"
              aria-selected={activeTab === tab}
              onClick={() => setActiveTab(tab)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                activeTab === tab
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-muted/70'
              }`}
            >
              {t(`tabs.${tab}`)}
            </button>
          ))}
        </div>

        <p className="rounded-lg bg-muted/40 p-3 text-xs leading-relaxed text-muted-foreground">
          {t(`scenario.${activeTab}`)}
        </p>

        {activeTab === 'link' ? (
          <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/30 p-3">
            <code className="flex-1 truncate text-xs text-foreground">{publicUrl}</code>
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={() => copy(publicUrl, setLinkCopied)}
            >
              {linkCopied ? (
                <Check className="mr-1.5 size-4" aria-hidden="true" />
              ) : (
                <Copy className="mr-1.5 size-4" aria-hidden="true" />
              )}
              {t(linkCopied ? 'link.copied' : 'link.copy')}
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            {activeTab === 'floating' ? (
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  {t('floating.buttonText')}
                  <input
                    className="min-h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={floatingText}
                    onChange={(event) => setFloatingText(event.target.value)}
                  />
                </label>
                <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                  {t('floating.position')}
                  <select
                    className="min-h-9 rounded-md border border-input bg-background px-3 text-sm"
                    value={floatingPosition}
                    onChange={(event) => setFloatingPosition(event.target.value as FloatingPosition)}
                  >
                    <option value="bottom-right">{t('floating.positions.bottomRight')}</option>
                    <option value="bottom-left">{t('floating.positions.bottomLeft')}</option>
                  </select>
                </label>
              </div>
            ) : null}

            {activeTab === 'modal' ? (
              <label className="grid gap-1 text-xs font-medium text-muted-foreground">
                {t('modal.selectorLabel')}
                <input
                  className="min-h-9 rounded-md border border-input bg-background px-3 text-sm"
                  value={modalSelector}
                  placeholder={t('modal.selectorPlaceholder')}
                  onChange={(event) => setModalSelector(event.target.value)}
                />
                <span className="font-normal normal-case text-muted-foreground/80">{t('modal.selectorHelp')}</span>
              </label>
            ) : null}

            <div role="tablist" aria-label={t('description')} className="flex gap-1.5">
              {(['html', 'react', 'iframe'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={format === value}
                  onClick={() => setFormat(value)}
                  className={`rounded-md px-2.5 py-1 text-xs font-semibold transition ${
                    format === value
                      ? 'bg-foreground text-background'
                      : 'bg-muted text-muted-foreground hover:bg-muted/70'
                  }`}
                >
                  {t(`format.${value}`)}
                </button>
              ))}
            </div>

            <pre className="max-h-56 overflow-auto rounded-lg border border-border bg-muted/30 p-3 text-xs text-foreground">
              <code>{snippet}</code>
            </pre>

            <Button type="button" size="sm" onClick={() => copy(snippet, setCodeCopied)}>
              {codeCopied ? (
                <Check className="mr-1.5 size-4" aria-hidden="true" />
              ) : (
                <Copy className="mr-1.5 size-4" aria-hidden="true" />
              )}
              {t(codeCopied ? 'codeCopied' : 'copyCode')}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
