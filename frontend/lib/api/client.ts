/**
 * Thin fetch wrapper for the FastAPI backend. Kept dependency-free (no
 * axios) so the frontend bundle stays small; swap for a generated
 * OpenAPI client as the API surface grows.
 */
import { getAccessToken } from "@/lib/auth/token";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export class ApiError extends Error {
  status: number;
  errorCode?: string;

  constructor(status: number, message: string, errorCode?: string) {
    super(message);
    this.status = status;
    this.errorCode = errorCode;
  }
}

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE" | "PATCH";
  body?: unknown;
  headers?: Record<string, string>;
  auth?: boolean;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, headers = {}, auth = true } = options;

  const finalHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (auth) {
    const token = getAccessToken();
    if (token) finalHeaders.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_URL}${path}`, {
    method,
    headers: finalHeaders,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });

  if (!response.ok) {
    let message = response.statusText;
    let errorCode: string | undefined;
    try {
      const data = await response.json();
      message = data.message ?? message;
      errorCode = data.error_code;
    } catch {
      // response body wasn't JSON — fall back to statusText
    }
    throw new ApiError(response.status, message, errorCode);
  }

  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
