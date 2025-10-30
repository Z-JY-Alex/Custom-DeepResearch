import asyncpg
from typing import List, Dict, Any, Optional


class AsyncPostgresDB:
    def __init__(self, user: str, password: str, database: str, host: str = "localhost", port: int = 5432):
        self.user = user
        self.password = password
        self.database = database
        self.host = host
        self.port = port
        self.pool: Optional[asyncpg.pool.Pool] = None

    async def connect(self):
        """初始化连接池"""
        self.pool = await asyncpg.create_pool(
            user=self.user,
            password=self.password,
            database=self.database,
            host=self.host,
            port=self.port,
            min_size=1,
            max_size=10
        )

    async def close(self):
        """关闭连接池"""
        if self.pool:
            await self.pool.close()

    async def fetch(self, query: str, *args) -> List[Dict[str, Any]]:
        """执行 SELECT 查询并返回结果列表"""
        if not self.pool:
            raise RuntimeError("连接池未初始化，请先调用 connect()")
        async with self.pool.acquire() as connection:
            rows = await connection.fetch(query, *args)
            return [dict(row) for row in rows]

    async def fetchrow(self, query: str, *args) -> Optional[Dict[str, Any]]:
        """执行 SELECT 查询并返回单行结果"""
        if not self.pool:
            raise RuntimeError("连接池未初始化，请先调用 connect()")
        async with self.pool.acquire() as connection:
            row = await connection.fetchrow(query, *args)
            return dict(row) if row else None

    async def execute(self, query: str, *args) -> str:
        """执行 INSERT/UPDATE/DELETE 等语句"""
        if not self.pool:
            raise RuntimeError("连接池未初始化，请先调用 connect()")
        async with self.pool.acquire() as connection:
            result = await connection.execute(query, *args)
            return result

if __name__ == "__main__":
    import asyncio
    
    async def main():
        db = AsyncPostgresDB(
            user='dify',
            password='Dify#123456',
            database='kg_course',
            host='10.0.2.75',
            port=15432
        )
        await db.connect()
        
        data = await db.fetch("select * from cc_course where course_id = '1000000326'")

        print(f"result: {data}")
        await db.close()
    
    asyncio.run(main())
    