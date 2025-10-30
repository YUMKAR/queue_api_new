import sqlite3
import time
import random

DB_FILE = "queue.db"

# DB 연결
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

# === 게임 ID 목록 ===
GAMES = ["1", "2", "3", "4", "5"]

# === 샘플 유저 목록 ===
PLAYERS = [
    ("홍길동", "01011112222"),
    ("김철수", "01022223333"),
    ("이영희", "01033334444"),
    ("박영수", "01044445555"),
    ("최민수", "01055556666"),
    ("정은지", "01066667777"),
]

# === queue 테이블에도 waiting 상태로 등록 (없을 경우만) ===
for name, phone in PLAYERS:
    try:
        cursor.execute(
            "INSERT INTO queue (name, phone_number, registered_at, status) VALUES (?, ?, ?, ?)",
            (name, phone, time.time(), "waiting"),
        )
    except sqlite3.IntegrityError:
        pass  # 이미 존재하면 무시

# === 모든 게임에 대해 rankings 데이터 자동 삽입 ===
for game_id in GAMES:
    for name, phone in PLAYERS:
        # 점수는 랜덤으로 생성
        if game_id == "2":
            # 2번 게임은 "시간" 단위 → 낮을수록 좋은 점수
            score = random.randint(60, 300)  # 1~5분 사이 (초 단위)
        else:
            # 나머지는 "점수" → 높을수록 좋은 점수
            score = random.randint(100, 500)

        try:
            cursor.execute(
                "INSERT INTO rankings (name, phone_number, game, score) VALUES (?, ?, ?, ?)",
                (name, phone, game_id, score),
            )
        except sqlite3.IntegrityError:
            # 이미 있으면 업데이트
            cursor.execute(
                "UPDATE rankings SET score = ? WHERE phone_number = ? AND game = ?",
                (score, phone, game_id),
            )

conn.commit()
conn.close()

print("✅ 모든 게임에 샘플 랭킹 데이터 삽입 완료!")
