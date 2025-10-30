import sqlite3
import time

DB_FILE = "queue.db"

# DB 연결
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# === queue 테이블 샘플 데이터 삽입 ===
sample_queue = [
    ("홍길동", "01011112222", time.time(), "waiting"),
    ("김철수", "01022223333", time.time(), "waiting"),
    ("이영희", "01033334444", time.time(), "called")
]

for name, phone, registered_at, status in sample_queue:
    try:
        cursor.execute(
            "INSERT INTO queue (name, phone_number, registered_at, status) VALUES (?, ?, ?, ?)",
            (name, phone, registered_at, status)
        )
    except sqlite3.IntegrityError:
        pass  # 이미 있는 번호는 무시

# === rankings 테이블 샘플 데이터 삽입 ===
sample_rankings = [
    ("홍길동", "01011112222", "1", 300),
    ("김철수", "01022223333", "1", 250),
    ("이영희", "01033334444", "2", 400),
    ("홍길동", "01055556666", "1", 280),  # 같은 이름 다른 번호
]

for name, phone, game, score in sample_rankings:
    try:
        cursor.execute(
            "INSERT INTO rankings (name, phone_number, game, score) VALUES (?, ?, ?, ?)",
            (name, phone, game, score)
        )
    except sqlite3.IntegrityError:
        pass  # 이미 있는 PK는 무시

conn.commit()
conn.close()

print("✅ 테스트용 데이터 삽입 완료!")
