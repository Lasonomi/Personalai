"""
Initialize MySQL database & tables.
Usage:
  1. Create empty database in MySQL: CREATE DATABASE personalai;
  2. Set DATABASE_URL in .env
  3. python init_db.py
"""
import asyncio
import sys
from dotenv import load_dotenv
load_dotenv()

from app.config import settings


async def main():
    print("=" * 50)
    print("  PersonalAI — MySQL Init")
    print("=" * 50)
    print("Mencoba menghubungkan ke database yang dikonfigurasi.")

    try:
        from app.database.connection import init_db, engine
        await init_db()
        print("\nTables created successfully!")
        print("Tables: users, platform_accounts, events, tasks, reminders, memories, ...")
        await engine.dispose()
        return True
    except Exception as e:
        print(f"\nERROR: database initialization failed ({type(e).__name__}).")
        print("\nChecklist:")
        print("  1. MySQL server running?")
        print("  2. Database 'personalai' already created?")
        print("     CREATE DATABASE personalai CHARACTER SET utf8mb4;")
        print("  3. DATABASE_URL di .env benar?")
        print("     mysql+aiomysql://root:password@localhost:3306/personalai")
        print("  4. pip install aiomysql")
        return False


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
