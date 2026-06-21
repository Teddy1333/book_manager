export async function api(path: string, options: RequestInit = {}): Promise<any> {
  const headers = new Headers(options.headers as HeadersInit | undefined);
  const isArrayBuffer = options.body instanceof ArrayBuffer;

  if (options.body && !isArrayBuffer && !(options.body instanceof FormData) && !headers.has('content-type')) {
    headers.set('content-type', 'application/json');
  }

  const res = await fetch(`/api/proxy${path}`, { ...options, headers });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const detail = err.detail;
    throw new Error(
      Array.isArray(detail)
        ? detail.map((d: { msg: string }) => d.msg).join(', ')
        : String(detail || res.statusText)
    );
  }

  if (res.status === 204) return null;
  return res.json();
}
