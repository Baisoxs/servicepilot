"""所有 ORM 模型的父类。

为什么要有 naming_convention？
    Alembic 的 autogenerate 会对比「模型」和「数据库里的表」。
    如果不给约束起固定名字，数据库自动生成的名字（比如 users_pkey、
    users_email_key）在不同机器上可能不一样，Alembic 就会误以为
    「索引变了」，每次 migration 都生成一堆无意义的改名。

    统一命名后，同一个约束在所有环境里名字一致，迁移脚本才稳定。
"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",  # 普通索引
    "uq": "uq_%(table_name)s_%(column_0_name)s",  # 唯一约束
    "ck": "ck_%(table_name)s_%(constraint_name)s",  # 检查约束
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",  # 外键
    "pk": "pk_%(table_name)s",  # 主键
}


class Base(DeclarativeBase):
    """继承它就能被 SQLAlchemy 当成表模型；所有表都注册到 Base.metadata。"""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
