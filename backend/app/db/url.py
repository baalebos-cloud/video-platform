"""
Helpers for turning a "however-you-copied-it" Postgres connection string
(e.g. pasted straight from Neon's dashboard, which uses libpq/psycopg
query params) into a URL + connect_args that actually work with the
asyncpg driver.

Why this exists:
- Neon's connection strings use `sslmode=require` and sometimes
  `channel_binding=require` — both are libpq/psycopg parameters.
  asyncpg's `connect()` has no such keyword arguments, so passing them
  straight through (which is what SQLAlchemy's asyncpg dialect does with
  any query-string params) raises
  `TypeError: connect() got an unexpected keyword argument 'sslmode'`.
- If a Neon *pooled* (PgBouncer, `-pooler` in the hostname) connection
  string is used, asyncpg's client-side prepared-statement cache breaks
  against PgBouncer's transaction-pooling mode
  (`prepared statement "..." does not exist`). Disabling that cache is
  the standard fix and is harmless on a direct (non-pooled) connection
  too, so it's applied unconditionally here.
- Neon *requires* SSL on every connection, full stop — so rather than
  relying on `?sslmode=require` surviving every copy/paste into an env
  var (it's already been accidentally dropped once), SSL is force-enabled
  whenever the hostname looks like a Neon endpoint (`*.neon.tech`),
  regardless of what query params are or aren't present in the URL.
"""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params understood by libpq/psycopg but not by asyncpg's connect().
_UNSUPPORTED_BY_ASYNCPG = {"sslmode", "channel_binding"}
_SSL_REQUIRED_VALUES = {"require", "verify-ca", "verify-full"}
_ALWAYS_SSL_HOST_SUFFIXES = (".neon.tech",)


def normalize_asyncpg_url(raw_url: str) -> tuple[str, dict]:
    """
    Returns (clean_url, connect_args) ready for create_async_engine(url,
    connect_args=connect_args). Safe to call on any Postgres URL,
    Neon-flavored or not — plain `postgresql+asyncpg://...` URLs with no
    query string pass through unchanged (aside from the statement-cache
    setting, which is always applied).
    """
    parts = urlsplit(raw_url)
    query_pairs = parse_qsl(parts.query, keep_blank_values=True)

    wants_ssl = any(
        key == "sslmode" and value in _SSL_REQUIRED_VALUES for key, value in query_pairs
    ) or (parts.hostname or "").endswith(_ALWAYS_SSL_HOST_SUFFIXES)

    clean_pairs = [(k, v) for k, v in query_pairs if k not in _UNSUPPORTED_BY_ASYNCPG]
    clean_query = urlencode(clean_pairs)
    clean_url = urlunsplit((parts.scheme, parts.netloc, parts.path, clean_query, parts.fragment))

    connect_args: dict = {"statement_cache_size": 0}
    if wants_ssl:
        connect_args["ssl"] = True

    return clean_url, connect_args
