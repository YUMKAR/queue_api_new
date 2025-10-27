import sqlite3
import os

DB_FILE = "queue.db"

# 기존 DB 파일 삭제
if os.path.exists(DB_FILE):
    os.remove(DB_FILE)
    print(f"기존 데이터베이스 '{DB_FILE}' 파일을 삭제했습니다.")

# 새로운 DB 생성 및 연결
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()
print(f"새로운 데이터베이스 '{DB_FILE}'를 생성했습니다.")

# === queue 테이블 생성 ===
cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone_number TEXT UNIQUE NOT NULL,
        registered_at REAL NOT NULL,
        status TEXT NOT NULL
    )
""")

# === rankings 테이블 생성 ===
# 주의: main.py와 일치하도록 game 컬럼 추가 + 복합 기본키 설정
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rankings (
        name TEXT NOT NULL,
        game TEXT NOT NULL,
        score INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (name, game)
    )
""")

conn.commit()
conn.close()
print("✅ DB 초기화 완료: 'queue' 및 'rankings' 테이블 생성됨.")
