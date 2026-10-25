export const apiRoot = 'http://127.0.0.1:8000/api/v1';

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'ApiError';
  }
}

function errorMessage(payload: unknown): string {
  if (typeof payload === 'object' && payload !== null && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((item: unknown) => {
      if (typeof item === 'object' && item !== null && 'msg' in item) return String(item.msg);
      return 'Invalid request value.';
    }).join(' ');
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

  let payload: unknown;
  if (response.status !== 204) {
    try {
      payload = await response.json();
    } catch {
      throw new ApiError(`The local API returned an invalid response (HTTP ${response.status}).`, response.status);
    }
  }
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status);
  return payload as T;
}
