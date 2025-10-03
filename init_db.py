# init_db.py
import sqlite3
import os

DB_FILE = "queue.db"

# 기존에 DB 파일이 존재하면 삭제합니다.
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print(f"기존 데이터베이스 '{DB_FILE}' 파일을 삭제했습니다.")

# 새로운 데이터베이스 파일을 생성하고 연결합니다.
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print(f"새로운 데이터베이스 '{DB_FILE}'를 생성했습니다.")

# queue 테이블을 생성합니다.
cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone_number TEXT UNIQUE NOT NULL,
        registered_at REAL NOT NULL,
        status TEXT NOT NULL
    )
""")

# rankings 테이블을 생성합니다.
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rankings (
        name TEXT PRIMARY KEY,
        score INTEGER NOT NULL DEFAULT 0
    )
""")
conn.commit()
conn.close()

print("DB 초기화가 성공적으로 완료되었습니다. 테이블이 준비되었습니다.")