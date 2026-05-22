export function getAdminAccessRedirect(
  status: number,
  locale: string,
  returnTo: string
): string | null {
  if (status === 401) {
    const params = new URLSearchParams({ returnTo });
    return `/api/auth/login?${params.toString()}`;
  }

  if (status === 403) {
    return `/${locale}/dashboard/no-access`;
  }

  return null;
}
