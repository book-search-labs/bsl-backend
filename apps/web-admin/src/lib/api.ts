export type FetchResult<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; statusText: string; body: unknown };

type FetchOptions = RequestInit & { timeoutMs?: number };

export async function fetchJson<T>(url: string, options: FetchOptions = {}): Promise<FetchResult<T>> {
  const { timeoutMs = 5000, ...init } = options;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const headers: Record<string, string> = { ...(init.headers ?? {}) } as Record<string, string>;
    if (!(init.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    const response = await fetch(url, {
      ...init,
      signal: controller.signal,
      headers,
    });

    const text = await response.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }

    if (!response.ok) {
      return { ok: false, status: response.status, statusText: response.statusText, body };
    }

    return { ok: true, status: response.status, data: body as T };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    const statusText = error instanceof Error && error.name === "AbortError" ? "timeout" : "network_error";
    return { ok: false, status: 0, statusText, body: message };
  } finally {
    clearTimeout(timeoutId);
  }
}
