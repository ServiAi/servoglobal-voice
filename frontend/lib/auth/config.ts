import { createHash, randomBytes } from 'node:crypto';

export type Auth0Config = {
  domain: string;
  clientId: string;
  clientSecret: string;
  audience: string;
  baseUrl: string;
};

export const accessTokenCookie = 'serviai_access_token';
export const authStateCookie = 'serviai_auth_state';
export const authReturnToCookie = 'serviai_auth_return_to';
export const authCodeVerifierCookie = 'serviai_auth_code_verifier';

export function getAuth0Config(origin?: string): Auth0Config {
  const domain = process.env.AUTH0_DOMAIN ?? '';
  const clientId = process.env.AUTH0_CLIENT_ID ?? '';
  const clientSecret = process.env.AUTH0_CLIENT_SECRET ?? '';
  const audience = process.env.AUTH0_AUDIENCE ?? '';
  const baseUrl = process.env.AUTH0_BASE_URL ?? origin ?? '';

  if (!domain || !clientId || !clientSecret || !audience || !baseUrl) {
    throw new Error('Auth0 frontend configuration is incomplete');
  }

  return {
    domain,
    clientId,
    clientSecret,
    audience,
    baseUrl: baseUrl.replace(/\/$/, '')
  };
}

export function createPkceVerifier(): string {
  return randomBytes(32).toString('base64url');
}

export function createPkceChallenge(verifier: string): string {
  return createHash('sha256').update(verifier).digest('base64url');
}

export function getAuthorizeUrl(config: Auth0Config, state: string, codeChallenge: string): string {
  const redirectUri = `${config.baseUrl}/api/auth/callback`;
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: config.clientId,
    redirect_uri: redirectUri,
    scope: 'openid profile email read:me',
    audience: config.audience,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256'
  });

  return `https://${config.domain}/authorize?${params.toString()}`;
}

export function normalizeReturnTo(returnTo: string | null): string {
  if (!returnTo || !returnTo.startsWith('/') || returnTo.startsWith('//')) {
    return '/es/dashboard';
  }
  return returnTo;
}
