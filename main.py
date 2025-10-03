# main.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import sqlite3
import time
import os

# CORS 미들웨어 임포트
from fastapi.middleware.cors import CORSMiddleware

# --- DB 설정 ---
conn = sqlite3.connect("queue.db", check_same_thread=False)
cursor = conn.cursor()

# 1. queue 테이블 (대기열 관리)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        phone_number TEXT UNIQUE NOT NULL,
        registered_at REAL NOT NULL,
        status TEXT NOT NULL
    )
""")

# 2. rankings 테이블 (점수 기반 랭킹 저장)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS rankings (
        name TEXT PRIMARY KEY,
        score INTEGER NOT NULL DEFAULT 0
    )
""")
conn.commit()


# --- Pydantic 모델 ---
class QueueEntry(BaseModel):
    id: int
    name: str
    phone_number: str
    registered_at: float
    status: str


class QueueData(BaseModel):
    name: str
    phone_number: str


class CompleteData(BaseModel):
    phone_number: str
    score: int


class RankingEntry(BaseModel):
    name: str
    score: int


# --- FastAPI 앱 및 WebSocket 관리자 ---
app = FastAPI(docs_url="/api/docs", openapi_url="/api/openapi.json")

# CORS 미들웨어 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용
    allow_credentials=True,
    allow_methods=["*"],  # 모든 HTTP 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


# --- 헬퍼 함수: 현재 대기열 및 랭킹 데이터 조회 ---
def get_queue_data():
    cursor.execute(
        "SELECT id, name, phone_number, registered_at, status FROM queue WHERE status IN ('waiting', 'called') ORDER BY registered_at ASC")
    queue_rows = cursor.fetchall()
    queue_list = [QueueEntry(id=row[0], name=row[1], phone_number=row[2], registered_at=row[3], status=row[4]) for row
                  in queue_rows]

    cursor.execute("SELECT name, score FROM rankings ORDER BY score DESC LIMIT 5")
    ranking_rows = cursor.fetchall()
    ranking_list = [RankingEntry(name=row[0], score=row[1]) for row in ranking_rows]

    return {
        "queue_list": [q.model_dump() for q in queue_list],
        "ranking_list": [r.model_dump() for r in ranking_list]
    }

@app.get('/')
def root():
    return FileResponse("clients/not_found.html")

# --- HTML 파일 서빙 엔드포인트 ---
@app.get("/admin")
async def get_admin():
    return FileResponse("clients/admin.html")


@app.get("/display")
async def get_display():
    return FileResponse("clients/display.html")


@app.get("/cancel")
async def get_cancel():
    return FileResponse("clients/cancel.html")


# --- API 엔드포인트 ---
@app.post("/api/v1/queue/register", response_model=QueueEntry)
async def register_user(queue_data: QueueData):
    try:
        cursor.execute("INSERT INTO queue (name, phone_number, registered_at, status) VALUES (?, ?, ?, ?)",
                       (queue_data.name, queue_data.phone_number, time.time(), "waiting"))
        conn.commit()
        last_id = cursor.lastrowid

        await manager.broadcast(json.dumps(get_queue_data()))

        return QueueEntry(id=last_id, name=queue_data.name, phone_number=queue_data.phone_number,
                          registered_at=time.time(), status="waiting")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 전화번호입니다.")


@app.post("/api/v1/queue/call-next")
async def call_next_user():
    cursor.execute(
        "SELECT id, name, phone_number FROM queue WHERE status = 'waiting' ORDER BY registered_at ASC LIMIT 1")
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="대기 중인 사용자가 없습니다.")

    user_id, user_name, phone_number = user
    cursor.execute("UPDATE queue SET status = ? WHERE id = ?", ("called", user_id))
    conn.commit()

    await manager.broadcast(json.dumps(get_queue_data()))

    return {"called_user_name": user_name, "phone_number": phone_number}


@app.post("/api/v1/queue/call-specific/{phone_number}")
async def call_specific_user(phone_number: str):
    cursor.execute("SELECT id, name FROM queue WHERE phone_number = ?", (phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{phone_number}'에 해당하는 사용자가 없습니다.")

    user_id, user_name = user
    cursor.execute("UPDATE queue SET status = ? WHERE id = ?", ("called", user_id))
    conn.commit()

    await manager.broadcast(json.dumps(get_queue_data()))

    return {"called_user_name": user_name, "phone_number": phone_number}


@app.post("/api/v1/queue/complete")
async def complete_user(complete_data: CompleteData):
    cursor.execute("SELECT name FROM queue WHERE phone_number = ?", (complete_data.phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{complete_data.phone_number}'에 해당하는 사용자가 없습니다.")

    user_name = user[0]
    cursor.execute("DELETE FROM queue WHERE phone_number = ?", (complete_data.phone_number,))

    cursor.execute("INSERT OR REPLACE INTO rankings (name, score) VALUES (?, ?)", (user_name, complete_data.score))
    conn.commit()

    await manager.broadcast(json.dumps(get_queue_data()))

    return {"message": f"'{user_name}'님의 서비스가 완료되고, 점수({complete_data.score})가 반영되었습니다."}


@app.post("/api/v1/queue/cancel")
async def cancel_user(queue_data: QueueData):
    cursor.execute("SELECT name FROM queue WHERE phone_number = ?", (queue_data.phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{queue_data.phone_number}'에 해당하는 사용자가 없습니다.")

    user_name = user[0]
    cursor.execute("DELETE FROM queue WHERE phone_number = ?", (queue_data.phone_number,))
    conn.commit()

    await manager.broadcast(json.dumps(get_queue_data()))

    return {"message": f"'{user_name}'님의 대기열 등록이 취소되었습니다."}


@app.websocket("/api/v1/queue/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_text(json.dumps(get_queue_data()))
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket Error: {e}")