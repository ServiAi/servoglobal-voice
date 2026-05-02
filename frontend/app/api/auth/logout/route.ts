import { NextRequest, NextResponse } from 'next/server';

import {
  accessTokenCookie,
  authCodeVerifierCookie,
  authReturnToCookie,
  authStateCookie,
  getAuth0Config
} from '@/lib/auth/config';

export async function GET(request: NextRequest) {
  const config = getAuth0Config(request.nextUrl.origin);
  const returnTo = `${config.baseUrl}/es`;
  const logoutUrl = new URL(`https://${config.domain}/v2/logout`);
  logoutUrl.searchParams.set('client_id', config.clientId);
  logoutUrl.searchParams.set('returnTo', returnTo);

  const response = NextResponse.redirect(logoutUrl);
  response.cookies.delete(accessTokenCookie);
  response.cookies.delete(authStateCookie);
  response.cookies.delete(authReturnToCookie);
  response.cookies.delete(authCodeVerifierCookie);
  return response;
}
