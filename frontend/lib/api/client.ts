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
      // Surface a safe field-level validation message instead of a generic 422.
      if (response.status === 422 && errorCode === "validation_error" && Array.isArray(data.details)) {
        const issue = data.details.find((item: { loc?: unknown; msg?: unknown }) =>
          Array.isArray(item.loc) && item.loc[0] === "body" && typeof item.msg === "string"
        );
        if (issue) {
          const field = (issue.loc as string[]).slice(1).join(".") || "Request";
          message = `${field}: ${issue.msg}`;
        }
      }
    } catch { /* non-JSON failure */ }
    throw new ApiError(response.status, message, errorCode);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
