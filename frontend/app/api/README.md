The /api/gateway route is a same-origin backend-for-frontend (BFF).
It exchanges login/signup JWTs for HttpOnly SameSite=Lax Secure cookies, rotates
database-backed refresh credentials, and forwards whitelisted headers to FastAPI.
Browser code must use apiRequest instead of direct FastAPI calls.

API_INTERNAL_URL is an optional server-only override. If absent the BFF
uses NEXT_PUBLIC_API_URL. The URL must end in /api/v1 and point to the
actual Render API. Restrict gateway access to the web origin; mutating calls
require an Origin header that matches request origin. Never expose tokens
from route handler responses. Old localStorage login sessions must sign in again.
