# import asyncio
# import uuid

# from sqlalchemy import select

# from packages.db.models import User
# from packages.db.session import SessionLocal


# async def main() -> None:
#     email = f"demo-{uuid.uuid4().hex[:6]}@example.com"

#     async with SessionLocal() as session:
#         # 1) 插入
#         user = User(email=email, password_hash="fake-hash")
#         session.add(user)              # 只是挂到 session 上，还没发 SQL
#         await session.commit()         # 这里才真正发 INSERT
#         print("inserted:", user.id, user.created_at)

#         # 2) 查询
#         result = await session.execute(select(User).where(User.email == email))
#         loaded = result.scalar_one()
#         print("loaded:", loaded.email)

#         # 3) 删除（清理，别留测试数据）
#         await session.delete(loaded)
#         await session.commit()


# if __name__ == "__main__":
#     asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)

import asyncio
import uuid

from packages.db.models import Conversation, Message, User
from packages.db.session import SessionLocal


async def main() -> None:
    email = f"demo-{uuid.uuid4().hex[:6]}@example.com"

    async with SessionLocal() as session:
        # 1) 建 user -> conversation -> message
        user = User(email=email, password_hash="fake-hash")
        session.add(user)
        await session.flush()  # 发 INSERT，拿到 user.id，但不提交

        conv = Conversation(user_id=user.id, title="demo chat")
        session.add(conv)
        await session.flush()

        msg = Message(conversation_id=conv.id, content="hello")
        session.add(msg)
        await session.commit()

        print("user:", user.id)
        print("conv:", conv.id)
        print("msg :", msg.id)

        # 2) 只删 user，看数据库级联
        await session.delete(user)
        await session.commit()
        print("deleted user")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
