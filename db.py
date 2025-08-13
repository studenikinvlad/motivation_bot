import aiosqlite
import logging
import os
from datetime import datetime
import pandas as pd
import glob

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
                usage_date TEXT,
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
        try:
            await db.execute("ALTER TABLE usage_requests ADD COLUMN usage_date TEXT")
            await db.commit()
        except aiosqlite.OperationalError:
            pass
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
    async def get_user_requests(self, user_id):
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
            SELECT id, description, status, created_at, usage_date
            FROM usage_requests
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user_id,))
            return await cursor.fetchall()
        
    async def delete_request(self, request_id, user_id=None):
        request_id = int(request_id)  # Явное преобразование
        if user_id is not None:
            user_id = int(user_id)  # Явное преобразование
        async with aiosqlite.connect(self.db_path) as db:
            if user_id:
                cursor = await db.execute(
                    "SELECT 1 FROM usage_requests WHERE id = ? AND user_id = ?",
                    (request_id, user_id)
                )
                if not await cursor.fetchone():
                    return False
            await db.execute("DELETE FROM usage_requests WHERE id = ?",
                             (request_id,))
            await db.commit()
            return True

    async def add_usage_request(self, user_id, description, usage_date=None):
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("""
                INSERT INTO usage_requests (user_id, description, usage_date)
                VALUES (?, ?, ?)
            """, (user_id, description, usage_date))
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

    # В класс Database добавим новый метод
    async def is_date_available(self, date: str, user_id: int = None) -> bool:
        """Проверяет, доступна ли дата для заявки (не более 3 заявок одного типа)"""
        async with aiosqlite.connect(self.db_path) as db:
            # Получаем информацию о пользователе, если user_id передан
            user_role = None
            if user_id:
                user = await self.get_user(user_id)
                if user:
                    user_role = user['role']
            
            # Если это заявка на уход раньше и мы знаем роль пользователя
            if user_role in ["Консультант", "УСМ"]:
                cursor = await db.execute("""
                    SELECT COUNT(*) 
                    FROM usage_requests r
                    JOIN users u ON r.user_id = u.id
                    WHERE DATE(r.usage_date) = ? 
                    AND r.status = 'approved'
                    AND u.role = ?
                    AND r.description LIKE 'Уйти на%'
                """, (date, user_role))
            else:
                # Для других типов заявок проверяем все
                cursor = await db.execute("""
                    SELECT COUNT(*) 
                    FROM usage_requests 
                    WHERE DATE(usage_date) = ? 
                    AND status = 'approved'
                """, (date,))
                
            count = await cursor.fetchone()
            return count[0] < 3 if count else True
        
    async def get_approved_requests_for_date(self, date: str, role: str = None):
        """Получает одобренные заявки на конкретную дату использования"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = """
                SELECT r.id, u.full_name, r.description, r.usage_date, u.role
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'approved' AND r.usage_date = ?
            """
            params = [date]
            
            if role:
                query += " AND u.role = ?"
                params.append(role)
                
            query += " ORDER BY r.usage_date"
            
            cursor = await db.execute(query, params)
            return await cursor.fetchall()   
        
    async def get_active_approved_requests(self):
        """Получает актуальные одобренные заявки:
        - Если есть usage_date: показываем только если дата >= сегодня
        - Если нет usage_date: показываем всегда
        """
        today = datetime.now().strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT r.id, u.full_name, r.description, r.created_at, r.usage_date
                FROM usage_requests r
                JOIN users u ON r.user_id = u.id
                WHERE r.status = 'approved'
                AND (r.usage_date IS NULL OR date(r.usage_date) >= date(?))
                ORDER BY 
                    CASE 
                        WHEN r.usage_date IS NULL THEN 0  -- Сначала заявки без даты
                        ELSE 1  -- Затем заявки с датой
                    END,
                    r.usage_date ASC  -- Сортировка по дате использования (если есть)
                LIMIT 10
            """, (today,))
            return await cursor.fetchall()

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
    
# --- Резервная копия ---
    async def create_backup(self):
        """Создает резервную копию базы данных в Excel"""
        max_backups = 10  # Максимальное количество хранимых бэкапов
        backups = sorted(glob.glob(os.path.join(backup_dir, "backup_*.xlsx")))
        if len(backups) >= max_backups:
            for old_backup in backups[:-max_backups]:
                try:
                    os.remove(old_backup)
                except:
                    pass

        try:
            backup_dir = 'backups'
            os.makedirs(backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(backup_dir, f"backup_{timestamp}.xlsx")
            
            async with aiosqlite.connect(self.db_path) as db:
                # Получаем только пользовательские таблицы (исключаем системные)
                cursor = await db.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' 
                    AND name NOT LIKE 'sqlite_%'
                """)
                tables = [row[0] for row in await cursor.fetchall()]
                
                if not tables:
                    raise Exception("В базе нет таблиц для резервирования")
                
                # Создаем новый Excel-файл
                with pd.ExcelWriter(backup_path, engine='openpyxl') as writer:
                    # Создаем временный лист, который потом удалим
                    temp_sheet = writer.book.create_sheet("temp")
                    
                    for table in tables:
                        try:
                            # Получаем данные таблицы
                            cursor = await db.execute(f"SELECT * FROM {table}")
                            columns = [desc[0] for desc in cursor.description]
                            data = await cursor.fetchall()
                            
                            if data:  # Создаем лист только если есть данные
                                df = pd.DataFrame(data, columns=columns)
                                df.to_excel(
                                    writer,
                                    sheet_name=table[:31],  # Максимум 31 символ для имени листа
                                    index=False
                                )
                        except Exception as e:
                            logging.error(f"Ошибка экспорта таблицы {table}: {e}")
                            continue
                    
                    # Удаляем временный лист
                    if 'temp' in writer.book.sheetnames:
                        writer.book.remove(writer.book['temp'])
                    
                    # Если не создано ни одного листа, создаем пустой с сообщением
                    if not writer.book.sheetnames:
                        ws = writer.book.create_sheet("Информация")
                        ws['A1'] = "Нет данных для экспорта"
            
            return backup_path
            
        except Exception as e:
            # Удаляем частично созданный файл при ошибке
            if os.path.exists(backup_path):
                os.remove(backup_path)
            raise Exception(f"Ошибка создания резервной копии: {str(e)}")
    
# --- Глобальный экземпляр ---
db = Database()

# --- При запуске ---
async def init_db():
    try:
        await db.connect()
        print("✅ Подключение к SQLite успешно.")
    except Exception as e:
        logging.error(f"Ошибка подключения к SQLite: {e}")
