import { fetchPublicForm } from '@/lib/api/crm';
import { PublicFormClient } from '@/components/forms/PublicFormClient';

type Props = {
  params: Promise<{ token: string }>;
};

export const dynamic = 'force-dynamic';

export default async function PublicFormPage({ params }: Props) {
  const { token } = await params;
  const result = await fetchPublicForm(token);
  if (!result.ok) {
    return (
      <main className="mx-auto grid min-h-screen max-w-2xl place-items-center px-6">
        <div className="grid gap-3 text-center">
          <div className="text-sm font-semibold uppercase tracking-wide text-teal-700">ServiGlobal IA</div>
          <h1 className="text-2xl font-bold text-foreground">Link invalido o expirado</h1>
          <p className="text-sm text-muted-foreground">{result.detail}</p>
        </div>
      </main>
    );
  }
  return <PublicFormClient token={token} initialData={result.data} />;
}
