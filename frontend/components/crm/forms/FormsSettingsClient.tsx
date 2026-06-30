'use client';

import { FormEvent, useState } from 'react';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  createAdminTenantForm,
  createTenantForm,
} from '@/lib/api/crm';
import type { TenantFormItem } from '@/types/crm';

type Props = {
  accessToken: string;
  initialForms: TenantFormItem[];
  mode?: 'tenant' | 'admin';
  tenantId?: string;
};

const DEFAULT_FIELDS = [
  { key: 'nombre', label: 'Nombre', field_type: 'text', required: true, position: 0 },
  { key: 'empresa', label: 'Empresa', field_type: 'text', required: false, position: 1 },
  { key: 'telefono', label: 'Telefono', field_type: 'phone', required: false, position: 2 },
  { key: 'correo', label: 'Correo', field_type: 'email', required: false, position: 3 },
  { key: 'necesidad_principal', label: 'Necesidad principal', field_type: 'textarea', required: true, position: 4 },
  { key: 'presupuesto_estimado', label: 'Presupuesto estimado', field_type: 'text', required: false, position: 5 },
  { key: 'comentarios', label: 'Comentarios', field_type: 'textarea', required: false, position: 6 },
];

export function FormsSettingsClient({ accessToken, initialForms, mode = 'tenant', tenantId }: Props) {
  const [forms, setForms] = useState(initialForms);
  const [name, setName] = useState('Diagnostico comercial');
  const [description, setDescription] = useState('Formulario de calificacion comercial.');
  const [message, setMessage] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setSaving(true);
    const payload = { name, description, status: 'active', fields: DEFAULT_FIELDS };
    const result = mode === 'admin' && tenantId
      ? await createAdminTenantForm(accessToken, tenantId, payload)
      : await createTenantForm(accessToken, payload);
    setSaving(false);
    if (!result.ok) {
      setMessage(result.detail);
      return;
    }
    setForms((current) => [result.data, ...current]);
    setMessage('Formulario creado.');
  };

  return (
    <div className="grid gap-6">
      <form onSubmit={submit} className="grid gap-3 rounded-md border border-border p-4">
        <div className="grid gap-3 md:grid-cols-2">
          <label className="grid gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Nombre</span>
            <input className="rounded-md border border-border bg-background px-3 py-2" value={name} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span className="font-medium text-muted-foreground">Descripcion</span>
            <input className="rounded-md border border-border bg-background px-3 py-2" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
        </div>
        <Button type="submit" disabled={saving} className="w-fit gap-2">
          <Plus className="h-4 w-4" />
          Crear formulario
        </Button>
        {message && <p className="text-sm text-muted-foreground">{message}</p>}
      </form>
      <div className="grid gap-3">
        {forms.map((form) => (
          <section key={form.id} className="rounded-md border border-border p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-foreground">{form.name}</h2>
                <p className="text-sm text-muted-foreground">{form.description}</p>
              </div>
              <span className="rounded-md border border-border px-2 py-1 text-xs">{form.status}</span>
            </div>
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {form.fields.map((field) => (
                <div key={field.id} className="text-sm text-muted-foreground">
                  {field.label}{field.required ? ' *' : ''}
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
