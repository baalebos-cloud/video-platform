import { NextRequest, NextResponse } from "next/server";

// Same-origin BFF: the browser never receives bearer or refresh tokens.
// All upstream locations are fixed by deployment config, not request input.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const UPSTREAM = (process.env.API_INTERNAL_URL ||
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/+$/, "");
const SECURE = process.env.NODE_ENV === "production";
const ACCESS = SECURE ? "__Host-baale-access" : "baale-access";
const REFRESH = SECURE ? "__Host-baale-refresh" : "baale-refresh";

function setTokens(response: NextResponse, values: {access_token: string; refresh_token: string}) {
  response.cookies.set(ACCESS, values.access_token, {
    httpOnly: true, secure: SECURE, sameSite: "lax", path: "/", maxAge: 60 * 60,
  });
  response.cookies.set(REFRESH, values.refresh_token, {
    httpOnly: true, secure: SECURE, sameSite: "lax", path: "/", maxAge: 14 * 24 * 60 * 60,
  });
}

function clearTokens(response: NextResponse) {
  // __Host- cookies must keep Secure+Path=/ even when being expired.
  for (const name of [ACCESS, REFRESH]) {
    response.cookies.set(name, "", {
      httpOnly: true, secure: SECURE, sameSite: "lax", path: "/", maxAge: 0,
    });
  }
}
const csrfSafe = (request: NextRequest) => {
  if (["GET", "HEAD", "OPTIONS"].includes(request.method)) return true;
  const origin = request.headers.get("origin");
  return !!origin && origin === new URL(request.url).origin;
};

async function handler(request: NextRequest, {params}: {params: {path: string[]}}) {
  if (!csrfSafe(request)) return NextResponse.json({detail: "Cross-origin request rejected"}, {status: 403});
  const path = params.path.join("/");
  if (!params.path.length || params.path.some(p => !p || p === "." || p === ".." || p.includes("/"))) {
    return NextResponse.json({detail: "Invalid path"}, {status: 400});
  }
  const target = `${UPSTREAM}/${path}${request.nextUrl.search}`;
  const contentType = request.headers.get("content-type");
  const isNarrationUpload = /^videos\\/[0-9a-f-]{36}\\/storyboard\\/scenes\\/[0-9a-f-]{36}\\/narration$/.test(path)
    && request.method === "POST";
  if (isNarrationUpload && (!contentType?.toLowerCase().startsWith("audio/")
    || Number(request.headers.get("content-length") || "0") > 3 * 1024 * 1024)) {
    return NextResponse.json({detail: "Voice upload must be an audio file under 3 MB"}, {status: 413});
  }
  // Avoid request.text() on binary WebM/MP3/WAV data. It destroys audio.
  const requestBody = ["GET", "HEAD"].includes(request.method)
    ? undefined : isNarrationUpload ? await request.arrayBuffer() : await request.text();
  if (isNarrationUpload && requestBody instanceof ArrayBuffer && requestBody.byteLength > 3 * 1024 * 1024) {
    return NextResponse.json({detail: "Voice upload exceeds 3 MB"}, {status: 413});
  }
  const idempotency = request.headers.get("idempotency-key");
  const adminStepUp = request.headers.get("x-admin-authorization");
  const forward = (token?: string, body = requestBody, url = target, method = request.method) => {
    const headers: Record<string, string> = {};
    if (contentType) headers["Content-Type"] = contentType;
    if (idempotency) headers["Idempotency-Key"] = idempotency;
    if (adminStepUp) headers["X-Admin-Authorization"] = adminStepUp;
    if (token) headers.Authorization = `Bearer ${token}`;
    return fetch(url, {method, headers, body, cache: "no-store", redirect: "manual"});
  };
  const currentAccess = request.cookies.get(ACCESS)?.value;
  const currentRefresh = request.cookies.get(REFRESH)?.value;

  if (path === "auth/logout" && request.method === "POST") {
    if (currentRefresh) await fetch(`${UPSTREAM}/auth/sessions/logout`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({refresh_token: currentRefresh}), cache: "no-store",
    }).catch(() => undefined);
    const out = NextResponse.json({ok: true});
    clearTokens(out);
    return out;
  }

  if (["auth/login", "auth/signup"].includes(path) && request.method === "POST") {
    const upstream = await forward();
    if (!upstream.ok) return new NextResponse(await upstream.text(), {
      status: upstream.status, headers: {"Content-Type": "application/json"},
    });
    const data = await upstream.json();
    if (!data.access_token || !data.refresh_token) return NextResponse.json({detail:"Invalid login response"}, {status: 502});
    const output = NextResponse.json({ok: true}, {status: upstream.status});
    setTokens(output, data);
    return output;
  }

  let upstream = await forward(currentAccess);
  let rotated: {access_token: string; refresh_token: string} | null = null;
  if (upstream.status === 401 && currentRefresh && !path.startsWith("auth/password-reset/")) {
    const renewal = await fetch(`${UPSTREAM}/auth/sessions/refresh`, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({refresh_token: currentRefresh}), cache: "no-store",
    });
    if (renewal.ok) {
      rotated = await renewal.json();
      upstream = await forward(rotated!.access_token);
    }
  }
  // Do not forward cache, Set-Cookie, redirect Location or other upstream
  // headers. Only benign content headers are passed to the browser.
  const response = new NextResponse(upstream.status === 204 ? null : await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: {"Content-Type": upstream.headers.get("content-type") || "application/json",
      "Cache-Control": "no-store"},
  });
  if (rotated) setTokens(response, rotated);
  if (upstream.status === 401 || (upstream.ok && ["auth/password/change", "auth/sessions/revoke-all"].includes(path))) {
    clearTokens(response);
  }
  return response;
}

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
