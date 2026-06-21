import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const API_BASE = process.env.API_BASE_URL ?? 'http://localhost:8000';

async function handler(req: NextRequest, { params }: { params: { path: string[] } }) {
  const pathStr = params.path.join('/');
  const search = req.nextUrl.searchParams.toString();
  const targetUrl = `${API_BASE}/${pathStr}${search ? `?${search}` : ''}`;

  const cookieStore = cookies();
  const token = cookieStore.get('auth_token')?.value;

  const reqHeaders = new Headers();
  const ct = req.headers.get('content-type');
  if (ct) reqHeaders.set('content-type', ct);
  if (token) reqHeaders.set('authorization', `Bearer ${token}`);

  let body: ArrayBuffer | undefined;
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    const buf = await req.arrayBuffer();
    if (buf.byteLength > 0) body = buf;
  }

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: req.method,
      headers: reqHeaders,
      body,
    });
  } catch {
    return NextResponse.json({ detail: 'Backend service is unavailable' }, { status: 503 });
  }

  const resHeaders = new Headers();
  const resCt = upstream.headers.get('content-type');
  if (resCt) resHeaders.set('content-type', resCt);

  // On login: extract token and set httpOnly cookie
  if (pathStr === 'token' && req.method === 'POST' && upstream.ok) {
    const data = await upstream.json();
    const res = NextResponse.json(data, { status: upstream.status, headers: resHeaders });
    if (data.access_token) {
      res.cookies.set('auth_token', data.access_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'lax',
        path: '/',
        maxAge: 60 * 60 * 24 * 7,
      });
    }
    return res;
  }

  const resBody = await upstream.arrayBuffer();

  // 204 No Content should not have a body
  if (upstream.status === 204) {
    return new NextResponse(null, { status: 204, headers: resHeaders });
  }

  return new NextResponse(resBody, { status: upstream.status, headers: resHeaders });
}

export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
