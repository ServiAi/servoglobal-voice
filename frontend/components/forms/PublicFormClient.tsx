'use client';

import { FormEvent, useState } from 'react';
import { Button } from '@/components/ui/button';
import { submitPublicForm } from '@/lib/api/crm';
import type { PublicFormResponse } from '@/types/crm';

type Props = {
  token: string;
  initialData: PublicFormResponse;
};

export function PublicFormClient({ token, initialData }: Props) {
  const [answers, setAnswers] = useState<Record<string, string | boolean | null>>({});
  const [status, setStatus] = useState<'idle' | 'saving' | 'success' | 'error'>('idle');
  const [message, setMessage] = useState('');
  const [hp, setHp] = useState('');

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setStatus('saving');
    const result = await submitPublicForm(token, answers, hp);
    if (!result.ok) {
      setStatus('error');
      setMessage(result.detail);
      return;
    }
    setStatus('success');
    setMessage('Formulario enviado correctamente.');
  };

  if (status === 'success') {
    return (
      <div className="mx-auto grid min-h-screen max-w-2xl place-items-center px-6">
        <div className="grid gap-3 text-center">
          <div className="text-sm font-semibold uppercase tracking-wide text-teal-700">ServiGlobal IA</div>
          <h1 className="text-2xl font-bold text-foreground">{message}</h1>
        </div>
      </div>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col justify-center gap-6 px-6 py-10">
      <div>
        <div className="text-sm font-semibold uppercase tracking-wide text-teal-700">ServiGlobal IA</div>
        <h1 className="mt-2 text-3xl font-bold text-foreground">{initialData.form.name}</h1>
        {initialData.form.description && <p className="mt-2 text-muted-foreground">{initialData.form.description}</p>}
      </div>
      <form onSubmit={submit} className="grid gap-4">
        <input className="hidden" value={hp} onChange={(e) => setHp(e.target.value)} tabIndex={-1} autoComplete="off" />
        {initialData.form.fields.map((field) => (
          <label key={field.id} className="grid gap-1 text-sm">
            <span className="font-medium text-muted-foreground">
              {field.label}{field.required ? ' *' : ''}
            </span>
            {field.field_type === 'textarea' ? (
              <textarea
                required={field.required}
                rows={4}
                className="rounded-md border border-border bg-background px-3 py-2"
                onChange={(e) => setAnswers((current) => ({ ...current, [field.key]: e.target.value }))}
              />
            ) : field.field_type === 'select' ? (
              <select
                required={field.required}
                className="rounded-md border border-border bg-background px-3 py-2"
                onChange={(e) => setAnswers((current) => ({ ...current, [field.key]: e.target.value }))}
              >
                <option value="" />
                {field.options.map((option) => <option key={option} value={option}>{option}</option>)}
              </select>
            ) : (
              <input
                required={field.required}
                type={field.field_type === 'email' ? 'email' : field.field_type === 'phone' ? 'tel' : 'text'}
                className="rounded-md border border-border bg-background px-3 py-2"
                onChange={(e) => setAnswers((current) => ({ ...current, [field.key]: e.target.value }))}
              />
            )}
          </label>
        ))}
        {status === 'error' && <p className="text-sm text-red-500">{message}</p>}
        <Button type="submit" disabled={status === 'saving'}>Enviar</Button>
      </form>
    </main>
  );
}
