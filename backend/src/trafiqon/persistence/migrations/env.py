"""Alembic environment. URL: config `sqlalchemy.url` if set, else TRAFIQON_DATABASE_URL."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from trafiqon.persistence.models import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or os.environ.get("TRAFIQON_DATABASE_URL")
    if not url:
        raise RuntimeError("set TRAFIQON_DATABASE_URL")
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
