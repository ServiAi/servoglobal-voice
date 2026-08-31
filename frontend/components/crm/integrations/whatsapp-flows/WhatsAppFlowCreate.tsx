'use client';

import { useState, useTransition } from 'react';
import { Blocks, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { createWhatsAppFlowAction } from '@/app/[locale]/crm/settings/integrations/whatsapp/flows/actions';
import { Button } from '@/components/ui/button';
import type { WhatsAppFlowCategory, WhatsAppFlowContextSchemaOption } from '@/types/whatsapp-flows';

type Props = { locale: string; schemas: WhatsAppFlowContextSchemaOption[] };

export function WhatsAppFlowCreate({ locale, schemas }: Props) {
  const t = useTranslations('crm.integrationsCatalog.whatsapp.flows.createPage');
  const router = useRouter();
  const [mode, setMode] = useState<'visual' | 'context_schema'>('visual');
  const [name, setName] = useState('');
  const [flowKey, setFlowKey] = useState('');
  const [category, setCategory] = useState<WhatsAppFlowCategory>('LEAD_GENERATION');
  const [schemaId, setSchemaId] = useState(schemas[0]?.id || '');
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  const submit = () => {
    setError(null);
    startTransition(async () => {
      const result = await createWhatsAppFlowAction({
        name,
        flow_key: flowKey,
        categories: [category],
        source_mode: mode,
        context_schema_id: mode === 'context_schema' ? schemaId : undefined,
      });
      if (!result.ok) return setError(result.detail || t('genericError'));
      router.push(`/${locale}/crm/settings/integrations/whatsapp/flows/${result.data.id}`);
    });
  };

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600">Flow Studio</p><h2 className="mt-2 text-2xl font-bold tracking-tight">{t('title')}</h2><p className="mt-2 text-sm text-muted-foreground">{t('description')}</p></div>
      <div className="grid gap-4 sm:grid-cols-2">
        {([{ value: 'visual', icon: Blocks }, { value: 'context_schema', icon: Sparkles }] as const).map(({ value, icon: Icon }) => <button key={value} type="button" onClick={() => setMode(value)} className={`rounded-2xl border p-5 text-left outline-none transition focus-visible:ring-2 focus-visible:ring-ring ${mode === value ? 'border-emerald-500 bg-emerald-50/70 shadow-sm dark:bg-emerald-950/20' : 'border-border bg-card hover:border-emerald-500/40'}`}><Icon className="size-6 text-emerald-600" /><span className="mt-4 block font-semibold">{t(`${value}.title`)}</span><span className="mt-1 block text-sm text-muted-foreground">{t(`${value}.description`)}</span></button>)}
      </div>
      <div className="grid gap-5 rounded-2xl border border-border bg-card p-6 sm:grid-cols-2">
        <label className="space-y-2"><span className="text-sm font-medium">{t('name')}</span><input value={name} onChange={(event) => setName(event.target.value)} className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm" /></label>
        <label className="space-y-2"><span className="text-sm font-medium">{t('key')}</span><input value={flowKey} onChange={(event) => setFlowKey(event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))} placeholder="lead_qualification" className="h-10 w-full rounded-lg border border-input bg-background px-3 font-mono text-sm" /></label>
        <label className="space-y-2"><span className="text-sm font-medium">{t('category')}</span><select value={category} onChange={(event) => setCategory(event.target.value as WhatsAppFlowCategory)} className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm">{['LEAD_GENERATION','APPOINTMENT_BOOKING','CONTACT_US','CUSTOMER_SUPPORT','SURVEY','SIGN_UP','SIGN_IN','OTHER'].map((item) => <option key={item}>{item}</option>)}</select></label>
        {mode === 'context_schema' ? <label className="space-y-2"><span className="text-sm font-medium">{t('schema')}</span><select value={schemaId} onChange={(event) => setSchemaId(event.target.value)} disabled={!schemas.length} className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"><option value="">{t('selectSchema')}</option>{schemas.map((schema) => <option key={schema.id} value={schema.id}>{schema.agent_name} · {schema.name} v{schema.version}</option>)}</select>{!schemas.length ? <span className="block text-xs text-amber-600">{t('noSchemas')}</span> : null}</label> : null}
      </div>
      {error ? <p role="alert" className="rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">{error}</p> : null}
      <div className="flex justify-end"><Button onClick={submit} disabled={pending || !name || !flowKey || (mode === 'context_schema' && !schemaId)}>{pending ? t('creating') : t('continue')}</Button></div>
    </div>
  );
}
