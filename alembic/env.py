import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from packages.core.config import get_settings
from packages.db import models  # noqa: F401
from packages.db.base import Base

#   alembic 自己不知道你的模型在哪、数据库连哪。env.py 就是它启动时执行的脚本，负责回答三个问题：

#   1. 连哪个库？ → 现在写死成 driver://user:pass@localhost/dbname，假的
#   2. 拿什么当「真相」去比对？ → target_metadata = None，空
#   3. 用同步还是异步连接？ → 模板已经给的是异步，这块不用你管


# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.


config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url)


# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(
        run_async_migrations(),
        loop_factory=asyncio.SelectorEventLoop,
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
