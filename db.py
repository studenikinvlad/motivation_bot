import asyncpg
import logging

DB_HOST = 'amvera-studenikinvlad-cnpg-botapp-rw'
DB_NAME = 'superdb'
DB_USER = 'tgapps'
DB_PASSWORD = 'qwerty'
DB_PORT = 5432

class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Подключение к базе данных и создание таблиц"""
        try:
            self.pool = await asyncpg.create_pool(
                user='tgapps',
                password='qwerty',
                database='superdb',
                host='amvera-studenikinvlad-cnpg-botapp-rw',
                port=5432
            )
            await self._create_tables()
            logging.info("✅ Подключение к PostgreSQL успешно.")
        except Exception as e:
            logging.error(f"Ошибка подключения к БД: {e}")
            raise

    async def _create_tables(self):
        """Создание необходимых таблиц в базе данных"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id BIGINT PRIMARY KEY,
                    full_name TEXT,
                    role TEXT,
                    points INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS usage_requests (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(id),
                    description TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS history (
                    id SERIAL PRIMARY KEY,
                    admin_id BIGINT,
                    user_id BIGINT,
                    points INTEGER,
                    reason TEXT,
                    timestamp TIMESTAMP DEFAULT NOW()
                );
            """)

    # --- Пользователи ---
    async def get_user(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)

    async def add_user(self, user_id, full_name, role):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (id, full_name, role, points)
                VALUES ($1, $2, $3, 0)
                ON CONFLICT (id) DO NOTHING
            """, user_id, full_name, role)

    async def get_all_users(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT * FROM users")

    async def delete_user(self, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM users WHERE id = $1", user_id)

    # --- Баллы ---
    async def add_points(self, admin_id, user_id, points, reason):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE users SET points = points + $1 WHERE id = $2
            """, points, user_id)
            await conn.execute("""
                INSERT INTO history (admin_id, user_id, points, reason)
                VALUES ($1, $2, $3, $4)
            """, admin_id, user_id, points, reason)

    async def get_history(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT * FROM history
                WHERE user_id = $1
                ORDER BY timestamp DESC
            """, user_id)

    async def get_employee_history(self, employee_id):
        return await self.get_history(employee_id)

    # --- Заявки ---
    async def add_usage_request(self, user_id, description):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO usage_requests (user_id, description)
                VALUES ($1, $2) RETURNING id
            """, user_id, description)
            return row['id']

    async def get_pending_requests(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT r.id, u.full_name, r.description, r.created_at
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'pending'
                ORDER BY r.created_at
            """)

    async def get_latest_approved_requests(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT r.id, u.full_name, r.description, r.created_at
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'approved'
                ORDER BY r.created_at DESC
                LIMIT 10
            """)

    async def get_request(self, request_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("""
                SELECT user_id, description, status, created_at
                FROM usage_requests WHERE id = $1
            """, request_id)

    async def approve_request(self, request_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE usage_requests SET status = 'approved' WHERE id = $1
            """, request_id)

    async def reject_request(self, request_id):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE usage_requests SET status = 'rejected' WHERE id = $1
            """, request_id)

    async def clear_approved_requests(self):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM usage_requests WHERE status = 'approved'
            """)


# --- Глобальный экземпляр ---
db = Database()

# --- При запуске ---
async def init_db():
    try:
        await db.connect()
        print("✅ Подключение к PostgreSQL успешно.")
    except Exception as e:
        logging.error(f"Ошибка подключения к БД: {e}")
