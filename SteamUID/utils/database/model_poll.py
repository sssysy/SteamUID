"""Steam 轮询数据表与全部处理逻辑。"""

from typing import TypeVar, Optional

from sqlmodel import Field, col, select
from sqlalchemy import UniqueConstraint, delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import BaseIDModel, with_session

T_SteamPoll = TypeVar("T_SteamPoll", bound="SteamPoll")


class SteamPoll(BaseIDModel, table=True):
    """按任务名称分类的通用数据表，只存不解析，value 由业务方编解码。"""

    __table_args__ = (
        UniqueConstraint("task_name", "key", name="uq_steampoll_task_key"),
        {"extend_existing": True},
    )

    task_name: str = Field(default="", index=True, title="任务名称")
    key: str = Field(default="", index=True, title="数据键")
    value: str = Field(default="", title="数据值")

    @classmethod
    @with_session
    async def upsert(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
        key: str,
        value: str,
    ) -> None:
        result = await session.execute(
            select(cls).where(col(cls.task_name) == task_name, col(cls.key) == key)
        )
        row = result.scalars().first()
        if row is None:
            session.add(cls(task_name=task_name, key=key, value=value))
            return

        row.value = value
        session.add(row)

    @classmethod
    @with_session
    async def get_row(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
        key: str,
    ) -> Optional[T_SteamPoll]:
        result = await session.execute(
            select(cls).where(col(cls.task_name) == task_name, col(cls.key) == key)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_value(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
        key: str,
    ) -> Optional[str]:
        result = await session.execute(
            select(col(cls.value)).where(
                col(cls.task_name) == task_name, col(cls.key) == key
            )
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_all(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
    ) -> list[T_SteamPoll]:
        result = await session.execute(
            select(cls).where(col(cls.task_name) == task_name)
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def get_keys(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
    ) -> list[str]:
        result = await session.execute(
            select(col(cls.key)).where(col(cls.task_name) == task_name)
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_row(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
        key: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(col(cls.task_name) == task_name, col(cls.key) == key)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0

    @classmethod
    @with_session
    async def delete_task(
        cls: type[T_SteamPoll],
        session: AsyncSession,
        task_name: str,
    ) -> int:
        result = await session.execute(
            delete(cls).where(col(cls.task_name) == task_name)
        )
        return result.rowcount if isinstance(result, CursorResult) else 0


@site.register_admin
class SteamPollAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="Steam轮询数据", icon="fa fa-clock-o")
    model = SteamPoll
