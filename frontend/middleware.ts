import createMiddleware from 'next-intl/middleware';
import type { NextRequest } from 'next/server';
import {locales, defaultLocale} from './i18n';

const intlMiddleware = createMiddleware({
  locales,
  defaultLocale,
  localePrefix: 'always',
  localeDetection: false
});

const EMBED_PATH_RE = /^\/(?:es|en)\/voice\/[^/]+\/embed\/?$/;

export default function middleware(request: NextRequest) {
  const response = intlMiddleware(request);
  if (EMBED_PATH_RE.test(request.nextUrl.pathname)) {
    response.headers.set('Content-Security-Policy', 'frame-ancestors *');
  }
  return response;
}

export const config = {
  matcher: ['/', '/(es|en)/:path*']
};
