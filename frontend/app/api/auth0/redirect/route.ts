import { NextRequest, NextResponse } from 'next/server';

/**
 * Auth0 Post-Login Redirect Endpoint
 * 
 * This endpoint is configured as the "Application Login URI" / "Post-Login Redirect URI"
 * in Auth0 Dashboard for the staging application.
 * 
 * When a user resets their password or completes first login via Auth0,
 * Auth0 calls this endpoint to redirect the user.
 * 
 * Instead of sending them to the public landing page (/es),
 * we redirect them to /api/auth/login so they authenticate with their new credentials.
 */
export async function GET(request: NextRequest) {
  // Use the request origin (frontend URL) not NEXT_PUBLIC_API_URL (backend URL)
  const baseUrl = request.nextUrl.origin;
  // Redirect to the internal login endpoint, NOT the public landing
  const loginUrl = new URL('/api/auth/login', baseUrl);
  
  return NextResponse.redirect(loginUrl);
}
