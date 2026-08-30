import asyncio
from app.db.connection import init_db
import app.db.models  # noqa: F401 - register models with Base.metadata

async def main():
    print("Initializing database tables...")
    await init_db()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
