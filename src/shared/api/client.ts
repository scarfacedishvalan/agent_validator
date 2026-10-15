const apiRoot = 'http://127.0.0.1:8000/api/v1';

function errorMessage(payload: unknown): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (typeof detail === 'object' && detail !== null && 'issues' in detail) {
      const issues = (detail as { issues: Array<{ message?: string }> }).issues;
      return issues.map((issue) => issue.message).filter(Boolean).join(' ');
    }
  }
  return 'The local API request failed.';
}

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiRoot}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    });
  } catch {
    throw new Error('Cannot reach the local API. Start the backend and retry.');
  }

  const payload: unknown = response.status === 204
    ? undefined
    : await response.json().catch(() => undefined);
  if (!response.ok) throw new Error(errorMessage(payload));
  return payload as T;
}
