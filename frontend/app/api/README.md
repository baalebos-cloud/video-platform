Reserved for optional Next.js Route Handlers acting as a thin
backend-for-frontend (BFF) — e.g. setting an httpOnly session cookie
after login instead of storing the JWT in localStorage
(see `lib/auth/token.ts` for the current, simpler approach and its
tradeoff). Empty by default: the frontend calls the FastAPI backend
directly for everything today.
