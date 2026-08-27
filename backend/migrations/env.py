"""Alembic environment. Loads DATABASE_URL from app settings and the shared
declarative Base's metadata (importing every model module registers it)."""
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.ai.orchestrator import models as ai_orchestrator_models  # noqa: F401
from app.ai.personal_finance import models as ai_personal_finance_models  # noqa: F401
from app.auth import models as auth_models  # noqa: F401
from app.cards import models as cards_models  # noqa: F401
from app.config import get_settings
from app.credit import models as credit_models  # noqa: F401
from app.database import Base
from app.fx import models as fx_models  # noqa: F401
from app.payments import models as payments_models  # noqa: F401
from app.transactions import models as transactions_models  # noqa: F401
from app.users import models as users_models  # noqa: F401
from app.wallets import models as wallets_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
