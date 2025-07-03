import aiosqlite
import logging
import os
from datetime import datetime

DB_PATH = 'database.sqlite3'

class Database:
    def __init__(self):
        self.db_path = DB_PATH

    async def connect(self):
        """Создание таблиц при первом запуске"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await self._create_tables(db)
            logging.info("✅ Подключение к SQLite успешно.")
        except Exception as e:
            logging.error(f"Ошибка подключения к SQLite: {e}")
            raise

    async def _create_tables(self, db):
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                full_name TEXT,
                role TEXT,
                points INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS usage_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                description TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                user_id INTEGER,
                points INTEGER,
                reason TEXT,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await db.commit()

    # --- Пользователи ---
    async def get_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            return await cursor.fetchone()

    async def add_user(self, user_id, full_name, role):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute("""
                    INSERT INTO users (id, full_name, role, points)
                    VALUES (?, ?, ?, 0)
                """, (user_id, full_name, role))
                await db.commit()
            except aiosqlite.IntegrityError:
                pass  # Пользователь уже существует

    async def get_all_users(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM users")
            return await cursor.fetchall()

    async def delete_user(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            await db.commit()

    # --- Баллы ---
    async def add_points(self, admin_id, user_id, points, reason, silent: bool = False):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE users SET points = points + ? WHERE id = ?", (points, user_id))

            if not silent:
                await db.execute("""
                    INSERT INTO history (admin_id, user_id, points, reason)
                    VALUES (?, ?, ?, ?)
                """, (admin_id, user_id, points, reason))

            await db.commit()

    async def get_history(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM history
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, (user_id,))
            return await cursor.fetchall()

    async def get_employee_history(self, employee_id):
        return await self.get_history(employee_id)

    # --- Заявки ---
    async def add_usage_request(self, user_id, description):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO usage_requests (user_id, description)
                VALUES (?, ?)
            """, (user_id, description))
            await db.commit()
            return cursor.lastrowid

    async def get_pending_requests(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.id, u.full_name, r.description, r.created_at
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'pending'
                ORDER BY r.created_at
            """)
            return await cursor.fetchall()

    async def get_latest_approved_requests(self):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.id, u.full_name, r.description, r.created_at
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'approved'
                ORDER BY r.created_at DESC
                LIMIT 10
            """)
            return await cursor.fetchall()

    async def get_request(self, request_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT user_id, description, status, created_at
                FROM usage_requests WHERE id = ?
            """, (request_id,))
            return await cursor.fetchone()

    async def approve_request(self, request_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE usage_requests SET status = 'approved' WHERE id = ?", (request_id,))
            await db.commit()

    async def reject_request(self, request_id):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE usage_requests SET status = 'rejected' WHERE id = ?", (request_id,))
            await db.commit()

    async def clear_approved_requests(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM usage_requests WHERE status = 'approved'")
            await db.commit()
    




# --- Глобальный экземпляр ---
db = Database()

# --- При запуске ---
async def init_db():
    try:
        await db.connect()
        print("✅ Подключение к SQLite успешно.")
    except Exception as e:
        logging.error(f"Ошибка подключения к SQLite: {e}")
