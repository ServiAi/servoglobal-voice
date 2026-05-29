import 'server-only';

import { cookies, headers } from 'next/headers';
import { redirect } from 'next/navigation';

import { fetchMeProfile, type MeProfile } from '@/lib/api/me';
import { accessTokenCookie, normalizeReturnTo } from '@/lib/auth/config';

type AdminAccessContext = {
  accessToken: string;
  profile: MeProfile;
};

export type AdminAccessFailure = {
  ok: false;
  status: number;
  detail: string;
  redirectTo: 'login' | 'no-access';
};

type AdminAccessResult =
  | { ok: true; context: AdminAccessContext }
  | AdminAccessFailure;

export async function getAccessToken(): Promise<string | undefined> {
  const cookieStore = await cookies();
  const token = cookieStore.get(accessTokenCookie)?.value;

  if (token) {
    return token;
  }

  const headerStore = await headers();
  const cookieHeader = headerStore.get('cookie');
  if (!cookieHeader) {
    return undefined;
  }

  const rawCookie = cookieHeader
    .split(';')
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${accessTokenCookie}=`));

  if (!rawCookie) {
    return undefined;
  }

  const rawToken = rawCookie.slice(accessTokenCookie.length + 1);
  try {
    return decodeURIComponent(rawToken);
  } catch {
    return rawToken;
  }
}

function adminLoginPath(returnTo: string): string {
  const params = new URLSearchParams({
    returnTo: normalizeReturnTo(returnTo),
  });

  return `/api/auth/login?${params.toString()}`;
}

function noAccessPath(locale: string): string {
  return `/${locale}/dashboard/no-access`;
}

export function redirectAdminAccessFailure(
  status: number,
  locale: string,
  returnTo: string
): void {
  if (status === 401) {
    redirect(adminLoginPath(returnTo));
  }

  if (status === 403) {
    redirect(noAccessPath(locale));
  }
}

export async function resolveInternalAdminAccess(): Promise<AdminAccessResult> {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return {
      ok: false,
      status: 401,
      detail: 'Authentication token is required',
      redirectTo: 'login',
    };
  }

  const result = await fetchMeProfile(accessToken);

  if (!result.ok) {
    return {
      ok: false,
      status: result.status,
      detail: result.detail,
      redirectTo: result.status === 401 ? 'login' : 'no-access',
    };
  }

  if (result.profile.is_internal !== true) {
    return {
      ok: false,
      status: 403,
      detail: 'Internal administrator access is required',
      redirectTo: 'no-access',
    };
  }

  return {
    ok: true,
    context: {
      accessToken,
      profile: result.profile,
    },
  };
}

export async function requireInternalAdminAccess(
  locale: string,
  returnTo: string
): Promise<AdminAccessContext> {
  const result = await resolveInternalAdminAccess();

  if (!result.ok) {
    if (result.redirectTo === 'login') {
      redirect(adminLoginPath(returnTo));
    }

    redirect(noAccessPath(locale));
  }

  return result.context;
}
