import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime

DB_PATH = "botdb.sqlite"
lock = threading.Lock()

@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            fio TEXT NOT NULL,
            role TEXT NOT NULL,
            points INTEGER DEFAULT 0
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS points_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            points INTEGER NOT NULL,
            reason TEXT NOT NULL,
            timestamp TEXT NOT NULL
        );
        """)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            timestamp TEXT NOT NULL
        );
        """)

def add_user(user_id, fio, role):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if cursor.fetchone():
            return False
        cursor.execute(
            "INSERT INTO users (user_id, fio, role) VALUES (?, ?, ?)",
            (user_id, fio, role)
        )
        return True

def delete_user(user_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

def get_user(user_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, fio, role, points FROM users WHERE user_id = ?", (user_id,))
        return cursor.fetchone()

def get_all_users():
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, fio, role FROM users")
        return cursor.fetchall()

def add_points(admin_id, user_id, points, reason):
    print(f"===> add_points called with: admin_id={admin_id}, user_id={user_id}, points={points}, reason={reason}")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET points = points + ? WHERE user_id = ?",
            (points, user_id)
        )
        print("[DB] Points updated.")
        cursor.execute(
            "INSERT INTO points_history (admin_id, user_id, points, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
            (admin_id, user_id, points, reason, timestamp)
        )
        print("[DB] History inserted.")

def get_points_history(user_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT admin_id, points, reason, timestamp FROM points_history WHERE user_id = ? ORDER BY timestamp DESC",
            (user_id,)
        )
        return cursor.fetchall()

def add_usage_request(user_id, description):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO usage_requests (user_id, description, status, timestamp) VALUES (?, ?, 'pending', ?)",
            (user_id, description, timestamp)
        )
        return cursor.lastrowid


def get_user_points_by_request_id(req_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.points
            FROM usage_requests ur
            JOIN users u ON ur.user_id = u.user_id
            WHERE ur.id = ?
        """, (req_id,))
        row = cursor.fetchone()
        return row[0] if row else None


def get_request(req_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, description, status, timestamp FROM usage_requests WHERE id=?", (req_id,))
        row = cursor.fetchone()
    return row



def get_pending_requests():
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, user_id, description, timestamp FROM usage_requests WHERE status = 'pending' ORDER BY timestamp ASC"
        )
        requests = cursor.fetchall()
        results = []
        for req_id, user_id, desc, ts in requests:
            cursor.execute("SELECT fio FROM users WHERE user_id = ?", (user_id,))
            fio = cursor.fetchone()
            fio = fio[0] if fio else "Неизвестный"
            results.append((req_id, fio, desc, ts))
        return results

def approve_request(req_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usage_requests SET status = 'approved' WHERE id = ?",
            (req_id,)
        )

def reject_request(req_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE usage_requests SET status = 'rejected' WHERE id = ?",
            (req_id,)
        )

def get_latest_approved_requests():
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ur.id, u.fio, ur.description, DATE(ur.timestamp) as date_only
            FROM usage_requests ur
            JOIN users u ON ur.user_id = u.user_id
            WHERE ur.status = 'approved'
            ORDER BY ur.timestamp DESC
            """
        )
        return cursor.fetchall()
    
def get_request_status(req_id):
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status FROM usage_requests WHERE id = ?",
            (req_id,)
        )
        result = cursor.fetchone()
        if result:
            return result[0]
        else:
            return None

def clear_approved_requests():
    with lock, get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usage_requests WHERE status = 'approved'")

init_db()
