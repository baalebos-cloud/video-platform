/** Same-origin API proxy; bearer tokens are stored only in HttpOnly cookies. */
export class ApiError extends Error {
  status: number;
  errorCode?: string;
  constructor(status: number, message: string, errorCode?: string) {
    super(message); this.status = status; this.errorCode = errorCode;
  }
}
interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
}
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {method = "GET", body, headers = {}} = options;
  const response = await fetch(`/api/gateway${path}`, {
    method, headers: {"Content-Type":"application/json", ...headers},
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store", credentials: "same-origin",
  });
  if (!response.ok) {
    let message = response.statusText, errorCode: string | undefined;
    try {
      const data = await response.json();
      message = data.message ?? (typeof data.detail === "string" ? data.detail : message);
      errorCode = data.error_code;
    } catch { /* non-JSON failure */ }
    throw new ApiError(response.status, message, errorCode);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
