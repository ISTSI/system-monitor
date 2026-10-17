// Cookie authentication and CSRF remain in memory. No browser storage holds a session or workspace.
let csrfToken: string | undefined;
let authGeneration = 0;

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function csrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const generation = authGeneration;
  const result = await request<{ csrf_token: string }>('/auth/csrf');
  if (generation !== authGeneration) throw new ApiError(409, 'SESSION_CHANGED', 'The session changed. Retry the action.');
  csrfToken = result.csrf_token;
  return csrfToken;
}

export function clearCsrf(): void { authGeneration += 1; csrfToken = undefined; }

export function detachOnPageHide(projectId: string, workspaceId: string): void {
  if (!csrfToken) return;
  // Best effort only. The server's bounded lease handles crashes and missed unload delivery.
  void fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/workspaces/${encodeURIComponent(workspaceId)}/detach`, {
    method: 'POST', credentials: 'same-origin', keepalive: true,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken }, body: '{}',
  }).catch(() => {});
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', await csrf());
  const generation = authGeneration;
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, { ...options, headers, credentials: 'same-origin', cache: 'no-store', signal: options.signal ?? AbortSignal.timeout(15000) });
  } catch {
    throw new ApiError(0, 'NETWORK_UNAVAILABLE', 'The server could not be reached. Check the connection and retry.');
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body && typeof body === 'object' && 'error' in body ? body.error : null;
    const code = error && typeof error === 'object' && 'code' in error && typeof error.code === 'string' ? error.code : 'REQUEST_FAILED';
    const message = error && typeof error === 'object' && 'message' in error && typeof error.message === 'string' ? error.message : 'The request could not be completed.';
    if (response.status === 401 && generation === authGeneration) {
      clearCsrf();
      window.dispatchEvent(new Event('si-session-ended'));
    }
    throw new ApiError(response.status, code, message);
  }
  if (generation === authGeneration && body && typeof body === 'object' && 'csrf_token' in body && typeof body.csrf_token === 'string') {
    if (path === '/auth/login') authGeneration += 1;
    csrfToken = body.csrf_token;
  }
  return body as T;
}

export function write<T>(path: string, body: unknown = {}, method = 'POST'): Promise<T> {
  return request<T>(path, { method, body: JSON.stringify(body) });
}

export function message(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed. Retry when the server is available.';
}
