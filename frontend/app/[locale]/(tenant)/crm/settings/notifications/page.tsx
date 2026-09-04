import { redirect } from 'next/navigation';

type Props = {
  params: Promise<{ locale: string }>;
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
};

export default async function LegacyNotificationsRedirect({ params, searchParams }: Props) {
  const { locale } = await params;
  const resolvedSearchParams = await searchParams;
  const query = new URLSearchParams();
  Object.entries(resolvedSearchParams).forEach(([key, value]) => {
    if (typeof value === 'string') query.set(key, value);
  });
  redirect(`/${locale}/automations/notifications${query.size ? `?${query}` : ''}`);
}
