import { redirect } from 'next/navigation';

type Props = {
  params: Promise<{ locale: string; slug: string[] }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function LegacyIntegrationDetailRedirect({ params, searchParams }: Props) {
  const { locale, slug } = await params;
  const resolvedSearchParams = await searchParams;
  const query = new URLSearchParams();
  Object.entries(resolvedSearchParams).forEach(([key, value]) => {
    if (typeof value === 'string') query.set(key, value);
  });
  redirect(`/${locale}/integrations/${slug.join('/')}${query.size ? `?${query}` : ''}`);
}
