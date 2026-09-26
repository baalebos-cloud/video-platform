import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from app.config.settings import get_settings
from app.db.session import Base
from app.db.url import normalize_asyncpg_url
from app.db.models import *  # noqa: F401,F403  (ensures all models are registered on Base.metadata)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
_clean_url, _connect_args = normalize_asyncpg_url(settings.database_url)
config.set_main_option("sqlalchemy.url", _clean_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # Built directly with create_async_engine (rather than
    # async_engine_from_config) so connect_args from normalize_asyncpg_url
    # — the Neon/asyncpg SSL + prepared-statement-cache fixes — are
    # actually applied to the migration connection too, not just the app.
    connectable = create_async_engine(
        _clean_url, poolclass=pool.NullPool, connect_args=_connect_args
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
