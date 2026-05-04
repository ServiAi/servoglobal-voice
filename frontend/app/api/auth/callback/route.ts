import { NextRequest, NextResponse } from 'next/server';

import {
  accessTokenCookie,
  authCodeVerifierCookie,
  authReturnToCookie,
  authStateCookie,
  type Auth0Config,
  getAuth0Config,
  normalizeReturnTo
} from '@/lib/auth/config';

function redirectNoAccess(config: Auth0Config): NextResponse {
  const response = NextResponse.redirect(new URL('/es/dashboard/no-access', config.baseUrl));
  response.cookies.delete(authStateCookie);
  response.cookies.delete(authReturnToCookie);
  response.cookies.delete(authCodeVerifierCookie);
  return response;
}

export async function GET(request: NextRequest) {
  const config = getAuth0Config(request.nextUrl.origin);
  const state = request.nextUrl.searchParams.get('state');
  const code = request.nextUrl.searchParams.get('code');
  const expectedState = request.cookies.get(authStateCookie)?.value;
  const codeVerifier = request.cookies.get(authCodeVerifierCookie)?.value;

  if (!state || !code || !expectedState || state !== expectedState || !codeVerifier) {
    return redirectNoAccess(config);
  }

  const tokenResponse = await fetch(`https://${config.domain}/oauth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      grant_type: 'authorization_code',
      client_id: config.clientId,
      client_secret: config.clientSecret,
      code,
      code_verifier: codeVerifier,
      redirect_uri: `${config.baseUrl}/api/auth/callback`
    }),
    cache: 'no-store'
  });

  if (!tokenResponse.ok) {
    return redirectNoAccess(config);
  }

  const payload = (await tokenResponse.json()) as {
    access_token?: string;
    expires_in?: number;
  };

  if (!payload.access_token) {
    return redirectNoAccess(config);
  }

  const returnTo = normalizeReturnTo(request.cookies.get(authReturnToCookie)?.value ?? null);
  const response = NextResponse.redirect(new URL(returnTo, config.baseUrl));
  response.cookies.set(accessTokenCookie, payload.access_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: payload.expires_in ?? 3600
  });
  response.cookies.delete(authStateCookie);
  response.cookies.delete(authReturnToCookie);
  response.cookies.delete(authCodeVerifierCookie);

  return response;
}
