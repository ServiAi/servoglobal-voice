'use client';

import { useMemo, useState, useTransition } from 'react';
import { ArrowDown, ArrowUp, Copy, Eye, FileJson, Layers3, Plus, Save, Send, Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import {
  cloneWhatsAppFlowAction,
  compileWhatsAppFlowAction,
  deleteWhatsAppFlowAction,
  deprecateWhatsAppFlowAction,
  publishWhatsAppFlowAction,
  syncWhatsAppFlowMetaAction,
  updateWhatsAppFlowAction,
} from '@/app/[locale]/(tenant)/crm/settings/integrations/whatsapp/flows/actions';
import { Button } from '@/components/ui/button';
import type {
  WhatsAppFlow,
  WhatsAppFlowBuilder,
  WhatsAppFlowComponent,
  WhatsAppFlowComponentType,
  WhatsAppFlowScreen,
} from '@/types/whatsapp-flows';

type Props = { locale: string; initialFlow: WhatsAppFlow; canEdit: boolean };
type MobilePanel = 'screens' | 'preview' | 'properties';
type PreviewTab = 'visual' | 'preview' | 'json';

const PALETTE: Array<{ group: 'content' | 'input' | 'actions'; type: WhatsAppFlowComponentType }> = [
  { group: 'content', type: 'heading' }, { group: 'content', type: 'body' },
  { group: 'input', type: 'text_input' }, { group: 'input', type: 'email_input' },
  { group: 'input', type: 'phone_input' }, { group: 'input', type: 'number_input' },
  { group: 'input', type: 'text_area' }, { group: 'input', type: 'dropdown' },
  { group: 'input', type: 'radio' }, { group: 'input', type: 'checkbox' },
  { group: 'input', type: 'date' }, { group: 'actions', type: 'footer' },
];

function nextId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}`.toLowerCase();
}

function componentTemplate(type: WhatsAppFlowComponentType): WhatsAppFlowComponent {
  const id = nextId(type);
  if (type === 'heading') return { id, type, text: 'Nuevo título' };
  if (type === 'body') return { id, type, text: 'Añade aquí una explicación breve.' };
  if (type === 'footer') return { id, type, label: 'Continuar', action: { type: 'complete' } };
  const options = type === 'dropdown' || type === 'radio' ? [{ id: 'option_1', title: 'Opción 1' }] : [];
  return { id, type, label: 'Nuevo campo', required: false, options };
}

function normalizeNavigation(screens: WhatsAppFlowScreen[]) {
  return screens.map((screen, index) => {
    const terminal = index === screens.length - 1;
    const components = screen.components.map((component) => component.type === 'footer' ? {
      ...component,
      label: component.label || (terminal ? 'Enviar' : 'Continuar'),
      action: terminal
        ? { type: 'complete' as const }
        : { type: 'navigate' as const, target_screen_id: screens[index + 1].id },
    } : component);
    return { ...screen, terminal, components };
  });
}

function moveItem<T>(items: T[], index: number, direction: -1 | 1) {
  const target = index + direction;
  if (target < 0 || target >= items.length) return items;
  const copy = [...items];
  [copy[index], copy[target]] = [copy[target], copy[index]];
  return copy;
}

export function WhatsAppFlowStudio({ locale, initialFlow, canEdit }: Props) {
  const t = useTranslations('crm.integrationsCatalog.whatsapp.flows.studio');
  const router = useRouter();
  const readOnly = !canEdit || ['published', 'deprecated'].includes(initialFlow.status);
  const [name, setName] = useState(initialFlow.name);
  const [builder, setBuilder] = useState<WhatsAppFlowBuilder>(initialFlow.builder);
  const [selectedScreenId, setSelectedScreenId] = useState(initialFlow.builder.screens[0].id);
  const [selectedComponentId, setSelectedComponentId] = useState<string | null>(null);
  const [mobilePanel, setMobilePanel] = useState<MobilePanel>('preview');
  const [previewTab, setPreviewTab] = useState<PreviewTab>('visual');
  const [compiled, setCompiled] = useState<Record<string, unknown> | null>(initialFlow.compiled_flow_json || null);
  const [errors, setErrors] = useState(initialFlow.validation_errors);
  const [notice, setNotice] = useState<{ kind: 'success' | 'error'; text: string } | null>(null);
  const [pending, startTransition] = useTransition();
  const selectedScreen = builder.screens.find((screen) => screen.id === selectedScreenId) || builder.screens[0];
  const selectedComponent = selectedScreen.components.find((component) => component.id === selectedComponentId) || null;
  const contextFields = initialFlow.context_schema_snapshot?.fields || [];

  const updateScreen = (next: WhatsAppFlowScreen) => setBuilder((current) => ({
    ...current,
    screens: current.screens.map((screen) => screen.id === next.id ? next : screen),
  }));
  const updateComponent = (next: WhatsAppFlowComponent) => updateScreen({
    ...selectedScreen,
    components: selectedScreen.components.map((component) => component.id === next.id ? next : component),
  });

  const save = async () => updateWhatsAppFlowAction(initialFlow.id, { name, builder });
  const run = (work: () => Promise<{ ok: boolean; detail?: string; data?: unknown }>, success: string) => {
    setNotice(null);
    startTransition(async () => {
      const result = await work();
      setNotice({ kind: result.ok ? 'success' : 'error', text: result.ok ? success : result.detail || t('errors.generic') });
      if (result.ok) router.refresh();
    });
  };
  const saveOnly = () => run(save, t('messages.saved'));
  const compile = () => {
    setNotice(null);
    startTransition(async () => {
      const saved = await save();
      if (!saved.ok) return setNotice({ kind: 'error', text: saved.detail || t('errors.generic') });
      const result = await compileWhatsAppFlowAction(initialFlow.id);
      if (!result.ok) return setNotice({ kind: 'error', text: result.detail || t('errors.generic') });
      setCompiled(result.data.compiled_flow_json);
      setPreviewTab('json');
      setNotice({ kind: 'success', text: t('messages.compiled') });
    });
  };
  const validateMeta = () => {
    setNotice(null);
    startTransition(async () => {
      const saved = await save();
      if (!saved.ok) return setNotice({ kind: 'error', text: saved.detail || t('errors.generic') });
      const result = await syncWhatsAppFlowMetaAction(initialFlow.id);
      if (!result.ok) return setNotice({ kind: 'error', text: result.detail || t('errors.generic') });
      setCompiled(result.data.compiled_flow_json || null);
      setErrors(result.data.validation_errors);
      setNotice({ kind: result.data.validation_errors.length ? 'error' : 'success', text: result.data.validation_errors.length ? t('messages.metaInvalid', { count: result.data.validation_errors.length }) : t('messages.metaValid') });
      router.refresh();
    });
  };
  const cloneVersion = () => {
    setNotice(null);
    startTransition(async () => {
      const result = await cloneWhatsAppFlowAction(initialFlow.id);
      if (!result.ok) return setNotice({ kind: 'error', text: result.detail || t('errors.generic') });
      router.push(`/${locale}/crm/settings/integrations/whatsapp/flows/${result.data.id}`);
    });
  };
  const deleteDraft = () => {
    setNotice(null);
    startTransition(async () => {
      const result = await deleteWhatsAppFlowAction(initialFlow.id);
      if (!result.ok) return setNotice({ kind: 'error', text: result.detail || t('errors.generic') });
      router.push(`/${locale}/crm/settings/integrations/whatsapp/flows`);
    });
  };

  const addScreen = () => {
    const id = `SCREEN_${builder.screens.length + 1}`;
    const screens = normalizeNavigation([...builder.screens, { id, title: t('newScreen'), terminal: true, components: [componentTemplate('footer')] }]);
    setBuilder({ ...builder, screens });
    setSelectedScreenId(id);
    setSelectedComponentId(null);
  };
  const deleteScreen = (index: number) => {
    if (builder.screens.length === 1) return;
    const screens = normalizeNavigation(builder.screens.filter((_, itemIndex) => itemIndex !== index));
    setBuilder({ ...builder, screens });
    setSelectedScreenId(screens[Math.min(index, screens.length - 1)].id);
    setSelectedComponentId(null);
  };
  const addComponent = (type: WhatsAppFlowComponentType) => {
    if (type === 'footer' && selectedScreen.components.some((component) => component.type === 'footer')) return;
    const component = componentTemplate(type);
    const footerIndex = selectedScreen.components.findIndex((item) => item.type === 'footer');
    const components = [...selectedScreen.components];
    components.splice(footerIndex < 0 ? components.length : footerIndex, 0, component);
    updateScreen({ ...selectedScreen, components });
    setSelectedComponentId(component.id);
  };

  const previewComponents = useMemo(() => selectedScreen.components.filter((component) => component.type !== 'footer'), [selectedScreen]);

  return (
    <div className="space-y-4 pb-10">
      <header className="flex flex-col gap-4 rounded-2xl border border-border bg-card p-5 shadow-xs lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0 flex-1"><p className="text-xs font-semibold uppercase tracking-[0.16em] text-emerald-600">{initialFlow.flow_key} · v{initialFlow.version}</p><input aria-label={t('flowName')} disabled={readOnly} value={name} onChange={(event) => setName(event.target.value)} className="mt-1 w-full bg-transparent text-2xl font-bold tracking-tight outline-none disabled:cursor-default" /><p className="mt-1 text-xs text-muted-foreground">{t(`statuses.${initialFlow.status}`)}{readOnly ? ` · ${t('readOnly')}` : ''}</p></div>
        <div className="flex flex-wrap gap-2">{!readOnly ? <><Button variant="outline" onClick={saveOnly} disabled={pending}><Save className="mr-2 size-4" />{t('save')}</Button><Button variant="outline" onClick={compile} disabled={pending}><FileJson className="mr-2 size-4" />{t('compile')}</Button><Button variant="outline" onClick={validateMeta} disabled={pending}><Eye className="mr-2 size-4" />{t('validate')}</Button><Button onClick={() => run(() => publishWhatsAppFlowAction(initialFlow.id), t('messages.published'))} disabled={pending || errors.length > 0}><Send className="mr-2 size-4" />{t('publish')}</Button></> : null}{initialFlow.status === 'published' && canEdit ? <Button onClick={cloneVersion}><Copy className="mr-2 size-4" />{t('newVersion')}</Button> : null}{initialFlow.status === 'published' && canEdit ? <Button variant="outline" onClick={() => run(() => deprecateWhatsAppFlowAction(initialFlow.id), t('messages.deprecated'))}>{t('deprecate')}</Button> : null}{!readOnly ? <Button variant="ghost" className="text-destructive" onClick={() => { if (window.confirm(t('deleteWarning'))) deleteDraft(); }}><Trash2 className="size-4" /><span className="sr-only">{t('delete')}</span></Button> : null}</div>
      </header>
      {notice ? <div role={notice.kind === 'error' ? 'alert' : 'status'} className={`rounded-lg border p-3 text-sm ${notice.kind === 'error' ? 'border-destructive/30 bg-destructive/10 text-destructive' : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200'}`}>{notice.text}</div> : null}
      {errors.length ? <section className="rounded-xl border border-red-300 bg-red-50 p-4 text-red-950 dark:bg-red-950/20 dark:text-red-100"><h2 className="font-semibold">{t('metaErrors', { count: errors.length })}</h2><div className="mt-3 space-y-2">{errors.map((error, index) => <div key={`${error.error}-${index}`} className="rounded-lg border border-red-200 bg-white/60 p-3 text-sm dark:bg-black/20"><p className="font-mono text-xs font-semibold">{error.error_type || error.error || t('error')}</p><p className="mt-1">{error.message}</p>{error.line_start ? <p className="mt-1 text-xs opacity-75">{t('line', { line: error.line_start })}</p> : null}</div>)}</div></section> : null}

      <div className="grid grid-cols-3 gap-2 rounded-lg bg-muted p-1 lg:hidden">{(['screens','preview','properties'] as const).map((panel) => <button key={panel} onClick={() => setMobilePanel(panel)} className={`rounded-md px-2 py-2 text-xs font-semibold ${mobilePanel === panel ? 'bg-background shadow-xs' : 'text-muted-foreground'}`}>{t(`panels.${panel}`)}</button>)}</div>
      <div className="grid min-h-[680px] overflow-hidden rounded-2xl border border-border bg-card lg:grid-cols-[250px_minmax(0,1fr)_300px]">
        <aside className={`${mobilePanel === 'screens' ? 'block' : 'hidden'} border-r border-border bg-muted/20 p-4 lg:block`}>
          <div className="flex items-center justify-between"><h2 className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">{t('screens')}</h2>{!readOnly ? <button onClick={addScreen} className="rounded-md p-1.5 text-emerald-600 hover:bg-emerald-500/10"><Plus className="size-4" /><span className="sr-only">{t('addScreen')}</span></button> : null}</div>
          <div className="mt-3 space-y-2">{builder.screens.map((screen, index) => <div key={screen.id} className={`rounded-xl border p-3 ${screen.id === selectedScreen.id ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20' : 'border-border bg-card'}`}><button className="w-full text-left" onClick={() => { setSelectedScreenId(screen.id); setSelectedComponentId(null); }}><span className="block text-sm font-semibold">{screen.title}</span><span className="mt-1 block font-mono text-[11px] text-muted-foreground">{screen.id}</span></button>{!readOnly ? <div className="mt-2 flex gap-1"><button onClick={() => setBuilder({ ...builder, screens: normalizeNavigation(moveItem(builder.screens, index, -1)) })} disabled={index === 0} className="rounded p-1 hover:bg-muted disabled:opacity-30"><ArrowUp className="size-3.5" /></button><button onClick={() => setBuilder({ ...builder, screens: normalizeNavigation(moveItem(builder.screens, index, 1)) })} disabled={index === builder.screens.length - 1} className="rounded p-1 hover:bg-muted disabled:opacity-30"><ArrowDown className="size-3.5" /></button><button onClick={() => deleteScreen(index)} disabled={builder.screens.length === 1} className="ml-auto rounded p-1 text-destructive hover:bg-destructive/10 disabled:opacity-30"><Trash2 className="size-3.5" /></button></div> : null}</div>)}</div>
          {!readOnly ? <div className="mt-6"><h3 className="text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground">{t('palette')}</h3>{(['content','input','actions'] as const).map((group) => <div key={group} className="mt-4"><p className="mb-2 text-[11px] font-semibold uppercase text-muted-foreground">{t(`groups.${group}`)}</p><div className="grid grid-cols-2 gap-1.5">{PALETTE.filter((item) => item.group === group).map((item) => <button key={item.type} onClick={() => addComponent(item.type)} disabled={item.type === 'footer' && selectedScreen.components.some((component) => component.type === 'footer')} className="rounded-lg border border-border bg-background px-2 py-2 text-left text-xs hover:border-emerald-500/50 disabled:cursor-not-allowed disabled:opacity-40">{t(`components.${item.type}`)}</button>)}</div></div>)}</div> : null}
        </aside>

        <main className={`${mobilePanel === 'preview' ? 'block' : 'hidden'} min-w-0 p-4 sm:p-6 lg:block`}>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3"><div className="flex rounded-lg bg-muted p-1">{(['visual','preview','json'] as const).map((tab) => <button key={tab} onClick={() => setPreviewTab(tab)} className={`rounded-md px-3 py-1.5 text-xs font-semibold ${previewTab === tab ? 'bg-background shadow-xs' : 'text-muted-foreground'}`}>{t(`tabs.${tab}`)}</button>)}</div><span className="text-xs text-muted-foreground">{selectedScreen.id}</span></div>
          {previewTab === 'json' ? <pre className="max-h-[580px] overflow-auto rounded-xl bg-slate-950 p-4 text-xs leading-5 text-emerald-200">{compiled ? JSON.stringify(compiled, null, 2) : t('noCompiledJson')}</pre> : (
            <div className="mx-auto max-w-sm rounded-[2rem] border-[7px] border-slate-900 bg-[#efeae2] p-3 shadow-xl dark:border-slate-700 dark:bg-[#101c22]">
              <div className="rounded-[1.35rem] bg-[#075e54] px-4 py-3 text-white"><p className="text-xs font-semibold">WhatsApp</p><p className="text-[10px] text-white/70">ServiGlobal Flow</p></div>
              <div className="my-4 rounded-xl bg-white p-4 shadow-sm dark:bg-[#202c33]"> <h3 className="text-base font-semibold">{selectedScreen.title}</h3><div className="mt-4 space-y-3">{previewComponents.map((component) => <PreviewComponent key={component.id} component={component} selected={previewTab === 'visual' && component.id === selectedComponentId} onSelect={() => { if (previewTab === 'visual') { setSelectedComponentId(component.id); setMobilePanel('properties'); } }} />)}</div>{selectedScreen.components.find((component) => component.type === 'footer') ? <button type="button" onClick={() => previewTab === 'visual' && setSelectedComponentId(selectedScreen.components.find((component) => component.type === 'footer')?.id || null)} className="mt-5 w-full rounded-lg bg-[#00a884] px-3 py-2.5 text-sm font-semibold text-white">{selectedScreen.components.find((component) => component.type === 'footer')?.label}</button> : null}</div>
            </div>
          )}
          {previewTab === 'visual' && !readOnly ? <div className="mx-auto mt-5 max-w-sm space-y-2">{selectedScreen.components.map((component, index) => <div key={component.id} className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-xs ${component.id === selectedComponentId ? 'border-emerald-500 bg-emerald-50 dark:bg-emerald-950/20' : 'border-border'}`}><button className="min-w-0 flex-1 truncate text-left" onClick={() => setSelectedComponentId(component.id)}>{t(`components.${component.type}`)} · {component.label || component.text}</button><button onClick={() => updateScreen({ ...selectedScreen, components: moveItem(selectedScreen.components, index, -1) })} disabled={index === 0}><ArrowUp className="size-3.5" /></button><button onClick={() => updateScreen({ ...selectedScreen, components: moveItem(selectedScreen.components, index, 1) })} disabled={index === selectedScreen.components.length - 1}><ArrowDown className="size-3.5" /></button><button onClick={() => { const copy = { ...component, id: nextId(component.type) }; updateScreen({ ...selectedScreen, components: [...selectedScreen.components.slice(0, index + 1), copy, ...selectedScreen.components.slice(index + 1)] }); setSelectedComponentId(copy.id); }} disabled={component.type === 'footer'}><Copy className="size-3.5" /></button><button onClick={() => { updateScreen({ ...selectedScreen, components: selectedScreen.components.filter((item) => item.id !== component.id) }); setSelectedComponentId(null); }} className="text-destructive"><Trash2 className="size-3.5" /></button></div>)}</div> : null}
        </main>

        <aside className={`${mobilePanel === 'properties' ? 'block' : 'hidden'} border-l border-border p-4 lg:block`}>
          <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-muted-foreground">{t('properties')}</h2>
          <div className="mt-4 space-y-4"><label className="block space-y-1.5"><span className="text-xs font-medium">{t('screenTitle')}</span><input disabled={readOnly} value={selectedScreen.title} onChange={(event) => updateScreen({ ...selectedScreen, title: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm" /></label>
          {selectedComponent ? <ComponentProperties component={selectedComponent} readOnly={readOnly} screens={builder.screens} contextFields={contextFields} update={updateComponent} t={t} /> : <div className="rounded-xl border border-dashed border-border p-5 text-center text-sm text-muted-foreground"><Layers3 className="mx-auto mb-2 size-5" />{t('selectComponent')}</div>}</div>
        </aside>
      </div>
    </div>
  );
}

function PreviewComponent({ component, selected, onSelect }: { component: WhatsAppFlowComponent; selected: boolean; onSelect: () => void }) {
  const shell = `w-full rounded-lg p-1 text-left ${selected ? 'ring-2 ring-emerald-500' : ''}`;
  if (component.type === 'heading') return <button className={shell} onClick={onSelect}><strong className="text-lg">{component.text}</strong></button>;
  if (component.type === 'body') return <button className={shell} onClick={onSelect}><span className="text-sm leading-6">{component.text}</span></button>;
  if (component.type === 'checkbox') return <button className={shell} onClick={onSelect}><span className="flex items-center gap-2 text-sm"><span className="size-4 rounded border border-slate-400" />{component.label}</span></button>;
  if (component.type === 'radio') return <button className={shell} onClick={onSelect}><span className="block text-xs font-medium">{component.label}</span>{component.options?.map((option) => <span key={option.id} className="mt-2 flex items-center gap-2 text-sm"><span className="size-4 rounded-full border border-slate-400" />{option.title}</span>)}</button>;
  if (component.type === 'dropdown') return <button className={shell} onClick={onSelect}><span className="block text-xs font-medium">{component.label}</span><span className="mt-1 block rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-500">{component.options?.[0]?.title || 'Selecciona'}</span></button>;
  return <button className={shell} onClick={onSelect}><span className="block text-xs font-medium">{component.label}{component.required ? ' *' : ''}</span><span className="mt-1 block min-h-9 rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-400">{component.placeholder || (component.type === 'date' ? 'AAAA-MM-DD' : '')}</span></button>;
}

function ComponentProperties({ component, readOnly, screens, contextFields, update, t }: { component: WhatsAppFlowComponent; readOnly: boolean; screens: WhatsAppFlowScreen[]; contextFields: Array<{ key: string; label: string; field_type: string }>; update: (component: WhatsAppFlowComponent) => void; t: ReturnType<typeof useTranslations> }) {
  const isContent = component.type === 'heading' || component.type === 'body';
  const optionsText = (component.options || []).map((option) => `${option.id}|${option.title}`).join('\n');
  return <div className="space-y-4 rounded-xl border border-border bg-muted/20 p-3"><p className="text-sm font-semibold">{t(`components.${component.type}`)}</p><label className="block space-y-1.5"><span className="text-xs font-medium">ID</span><input disabled={readOnly} value={component.id} onChange={(event) => update({ ...component, id: event.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_') })} className="h-9 w-full rounded-md border border-input bg-background px-2.5 font-mono text-xs" /></label>{isContent ? <label className="block space-y-1.5"><span className="text-xs font-medium">{t('text')}</span><textarea disabled={readOnly} value={component.text || ''} onChange={(event) => update({ ...component, text: event.target.value })} rows={4} className="w-full rounded-md border border-input bg-background p-2.5 text-sm" /></label> : <label className="block space-y-1.5"><span className="text-xs font-medium">{t('label')}</span><input disabled={readOnly} value={component.label || ''} onChange={(event) => update({ ...component, label: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm" /></label>}{!isContent && component.type !== 'footer' ? <><label className="block space-y-1.5"><span className="text-xs font-medium">{t('placeholder')}</span><input disabled={readOnly} value={component.placeholder || ''} onChange={(event) => update({ ...component, placeholder: event.target.value })} className="h-9 w-full rounded-md border border-input bg-background px-2.5 text-sm" /></label><label className="flex items-center gap-2 text-sm"><input type="checkbox" disabled={readOnly} checked={component.required || false} onChange={(event) => update({ ...component, required: event.target.checked })} />{t('required')}</label>{contextFields.length ? <label className="block space-y-1.5"><span className="text-xs font-medium">{t('binding')}</span><select disabled={readOnly} value={component.binding?.context_field_key || ''} onChange={(event) => update({ ...component, binding: event.target.value ? { context_field_key: event.target.value } : null })} className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"><option value="">—</option>{contextFields.map((field) => <option key={field.key} value={field.key}>{field.label} · {field.key}</option>)}</select></label> : null}</> : null}{(component.type === 'dropdown' || component.type === 'radio') ? <label className="block space-y-1.5"><span className="text-xs font-medium">{t('options')}</span><textarea disabled={readOnly} value={optionsText} onChange={(event) => update({ ...component, options: event.target.value.split('\n').map((line) => line.split('|')).filter(([id, title]) => id?.trim() && title?.trim()).map(([id, title]) => ({ id: id.trim(), title: title.trim() })) })} rows={5} className="w-full rounded-md border border-input bg-background p-2 font-mono text-xs" /><span className="text-[11px] text-muted-foreground">id|{t('optionTitle')}</span></label> : null}{component.type === 'footer' && component.action?.type === 'navigate' ? <label className="block space-y-1.5"><span className="text-xs font-medium">{t('target')}</span><select disabled={readOnly} value={component.action.target_screen_id || ''} onChange={(event) => update({ ...component, action: { type: 'navigate', target_screen_id: event.target.value } })} className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm">{screens.map((screen) => <option key={screen.id} value={screen.id}>{screen.title}</option>)}</select></label> : null}</div>;
}
