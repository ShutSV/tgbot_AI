from abc import ABC, abstractmethod
from sqlalchemy import (BIGINT,
                        Column,
                        delete,
                        func,
                        insert,
                        INT,
                        select,
                        TIMESTAMP,
                        update,
                        VARCHAR,
                        )
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from settings import settings


DB_URL = settings.DATABASE_PRIVATE_URL.unicode_string().replace('postgresql', 'postgresql+asyncpg')


class Base(DeclarativeBase):
    id = Column(INT, primary_key=True)
    async_engine = create_async_engine(DB_URL)
    session = async_sessionmaker(bind=async_engine)


class UserChat(Base):
    __tablename__ = "user_chat"
    user_id = Column(BIGINT, nullable=False, unique=False)
    chat_id = Column(BIGINT, nullable=False, unique=False)
    assistant_id = Column(VARCHAR(255), nullable=False, unique=False)
    thread_id = Column(VARCHAR(255), nullable=False, unique=False)
    date_thread = Column(TIMESTAMP, nullable=False, unique=False, server_default=func.now())

    def __str__(self):
        return f"{self.user_id} {self.assistant_id} {self.thread_id} {self.date_thread}"

    def __repr__(self) -> str:
        return str(self)


async def create_table():
    async with Base.async_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


class AbstractRepository(ABC):
    @classmethod
    @abstractmethod
    async def get(cls, pk):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def all(cls):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def filter(cls, **kwargs):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def add(cls, instance):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def update(cls, pk, **kwargs):
        raise NotImplementedError

    @classmethod
    @abstractmethod
    async def delete(cls, pk):
        raise NotImplementedError


class SQLAlchemyRepository(AbstractRepository):
    model: Base
    session = Base.session

    @classmethod
    async def get(cls, pk):
        async with cls.session() as s:
            response = await s.execute(select(cls.model).where(cls.model.id == pk))
            return response.scalars().unique().all()

    @classmethod
    async def all(cls):
        async with cls.session() as s:
            response = await s.execute(select(cls.model))
            return response.scalars().unique().all()

    @classmethod
    async def filter(cls, **kwargs):
        async with cls.session() as s:
            response = await s.execute(select(cls.model).filter_by(**kwargs))
            return response.scalars().unique().all()

    @classmethod
    async def add(cls, instance):
        async with cls.session() as s:
            await s.execute(insert(cls.model).values(instance))
            await s.commit()

    @classmethod
    async def update(cls, pk, **kwargs):
        async with cls.session() as s:
            await s.execute(update(cls.model).filter_by(id=pk).values(**kwargs))
            await s.commit()

    @classmethod
    async def delete(cls, pk):
        async with cls.session() as s:
            await s.execute(delete(cls.model).filter_by(id=pk))
            await s.commit()


class UserChatRepository(SQLAlchemyRepository):
    model = UserChat
