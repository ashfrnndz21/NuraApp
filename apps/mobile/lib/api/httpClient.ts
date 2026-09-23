import { apiConfig, getSessionToken } from './config';
import { ApiRefusalError } from './refusals';

async function request<T>(
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH',
  path: string,
  body?: unknown,
): Promise<T> {
  const token = getSessionToken();
  const headers: Record<string, string> = { 'content-type': 'application/json' };
  if (token) headers.authorization = `Bearer ${token}`;

  const res = await fetch(`${apiConfig.baseUrl}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (res.status === 204) return undefined as T;

  const json = await res.json().catch(() => null);

  if (!res.ok) {
    if (json && typeof json === 'object' && 'refusal' in json) {
      throw new ApiRefusalError({ refusal: String(json.refusal), scope: json.scope, status: res.status });
    }
    // A route this client hasn't reached (network, 404, 422 body-shape mismatch, 5xx with no
    // `refusal` body) — surfaced the same honest, generic way as an unnamed refusal.
    throw new ApiRefusalError({ refusal: 'Unreachable', status: res.status });
  }

  return json as T;
}

export const http = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
};
