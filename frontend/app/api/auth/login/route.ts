import { NextRequest, NextResponse } from 'next/server';

import {
  authCodeVerifierCookie,
  authReturnToCookie,
  authStateCookie,
  createPkceChallenge,
  createPkceVerifier,
  getAuth0Config,
  getAuthorizeUrl,
  normalizeReturnTo
} from '@/lib/auth/config';

export async function GET(request: NextRequest) {
  const config = getAuth0Config(request.nextUrl.origin);
  const state = crypto.randomUUID();
  const codeVerifier = createPkceVerifier();
  const codeChallenge = createPkceChallenge(codeVerifier);
  const returnTo = normalizeReturnTo(request.nextUrl.searchParams.get('returnTo'));
  const response = NextResponse.redirect(getAuthorizeUrl(config, state, codeChallenge));

  response.cookies.set(authStateCookie, state, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 600
  });
  response.cookies.set(authReturnToCookie, returnTo, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 600
  });
  response.cookies.set(authCodeVerifierCookie, codeVerifier, {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: 600
  });

  return response;
}
