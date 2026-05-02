import { cookies } from 'next/headers';

import { accessTokenCookie } from '@/lib/auth/config';

export async function getAccessToken(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(accessTokenCookie)?.value;
}
