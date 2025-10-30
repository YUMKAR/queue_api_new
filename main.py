# main_fixed.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional, Generator
import json
import sqlite3
import time

# CORS 미들웨어 임포트
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# --- DB 설정 ---
DB_FILE = "queue.db"


def get_db_conn() -> Generator[sqlite3.Connection, None, None]:
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # 컬럼 이름으로 접근 가능하도록 설정
    try:
        yield conn
    finally:
        conn.close()


# 관리할 게임 목록
GAMES = ["1","2","3","4","5"]


# 마이그레이션: 앱 시작 전에 안전하게 마이그레이션 시도
def try_migrate_rankings_schema():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(rankings)")
        rows = cursor.fetchall()
        cols = [row[1] for row in rows]
        if cols and 'game' not in cols:
            print("[DB MIGRATE] Detected old 'rankings' schema without 'game' column. Migrating...")
            # --- rankings 테이블 초기화 부분 ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS rankings (
                    name TEXT NOT NULL,
                    phone_number TEXT NOT NULL,
                    game TEXT NOT NULL,
                    score INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (name, game, phone_number)
                )
            """)
            default_game = GAMES[0]
            try:
                # 기존 데이터가 있다면 기본 게임으로 마이그레이션
                cursor.execute("INSERT OR REPLACE INTO rankings_new (name, game, score) SELECT name, ?, score FROM rankings", (default_game,))
            except Exception:
                # 기존 테이블이 없거나 비어 있으면 무시
                pass
            cursor.execute("DROP TABLE IF EXISTS rankings")
            cursor.execute("ALTER TABLE rankings_new RENAME TO rankings")
            conn.commit()
            print("[DB MIGRATE] Migration complete. Existing rankings moved to game=", default_game)
        conn.close()
    except Exception as e:
        print("[DB MIGRATE] Migration check failed:", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 애플리케이션 시작 시
    print("Application startup: Initializing database...")
    # 마이그레이션 먼저 시도
    try_migrate_rankings_schema()

    conn = sqlite3.connect(DB_FILE)
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
            name TEXT NOT NULL,
            game TEXT NOT NULL,
            score INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (name, game)
        )
    """)
    conn.commit()
    conn.close()
    print("Database initialized.")
    yield
    # 애플리케이션 종료 시
    print("Application shutdown.")


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
    game: str


class RankingEntry(BaseModel):
    name: str
    phone_number: str  # 새로 추가
    score: int
    game: Optional[str] = None


class FullRankingEntry(BaseModel):
    name: str
    phone_number: str  # 새로 추가
    score: int
    game: str



# --- FastAPI 앱 및 WebSocket 관리자 ---
app = FastAPI(lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")

# CORS 미들웨어 설정 (개발용: 실제 배포 시 도메인 제한 권장)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        # store dicts: {"ws": WebSocket, "mode": "full"|"queue"}
        self.active_connections: List[Dict[str, object]] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        mode = websocket.query_params.get("mode", "full")
        self.active_connections.append({"ws": websocket, "mode": mode})
        return mode

    def disconnect(self, websocket: WebSocket):
        # remove the connection dict matching websocket
        self.active_connections = [c for c in self.active_connections if c.get("ws") is not websocket]

    async def broadcast(self, db_conn: sqlite3.Connection):
        # prepare full data once
        full_data = get_queue_data(db_conn)
        for conn_info in list(self.active_connections):
            ws: WebSocket = conn_info.get("ws")
            mode = conn_info.get("mode", "full")
            try:
                if mode == "queue":
                    # send only queue_list
                    payload = json.dumps({"queue_list": full_data.get("queue_list", [])})
                else:
                    payload = json.dumps(full_data)
                await ws.send_text(payload)
            except Exception as e:
                # on error, remove connection
                try:
                    self.disconnect(ws)
                except Exception:
                    pass
                print(f"WebSocket send error: {e}")


manager = ConnectionManager()


def get_queue_data(conn: sqlite3.Connection):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, phone_number, registered_at, status FROM queue WHERE status IN ('waiting', 'called') ORDER BY registered_at ASC")
    queue_rows = cursor.fetchall()
    queue_list = [QueueEntry(**dict(row)) for row in queue_rows]

    # 게임별 상위 5명 랭킹을 phone_number 포함해서 반환
    ranking_dict = {}
    for game in GAMES:
        cursor.execute("SELECT name, phone_number, score FROM rankings WHERE game = ? ORDER BY score DESC LIMIT 5", (game,))
        ranking_rows = cursor.fetchall()
        ranking_list = [
            RankingEntry(
                name=row["name"],
                phone_number=row["phone_number"],
                score=row["score"],
                game=game
            ) for row in ranking_rows
        ]
        ranking_dict[game] = [r.model_dump() for r in ranking_list]

    return {
        "queue_list": [q.model_dump() for q in queue_list],
        "ranking_list": ranking_dict
    }




@app.get('/')
def root():
    return FileResponse("clients/not_found.html")


# --- API 엔드포인트: 게임 목록 ---
@app.get("/api/v1/games")
async def get_games():
    """사용 가능한 게임 목록을 반환합니다."""
    return {"games": GAMES}


# --- HTML 파일 서빙 엔드포인트 ---
@app.get("/admin")
async def get_admin():
    return FileResponse("clients/admin.html")

@app.get("/ranking/admin")
async def get_admin():
    return FileResponse("clients/all_ranking.html")


@app.get("/display")
async def get_display():
    return FileResponse("clients/display_queue_page.html")


@app.get("/ranking")
async def get_ranking_page():
    return FileResponse("clients/display_ranking_page.html")


@app.get("/cancel")
async def get_cancel():
    return FileResponse("clients/cancel.html")


@app.get("/register")
async def get_register():
    return FileResponse("clients/register.html")

# --- API 엔드포인트 ---
@app.post("/api/v1/queue/register", response_model=QueueEntry)
async def register_user(queue_data: QueueData, conn: sqlite3.Connection = Depends(get_db_conn)):
    try:
        cursor = conn.cursor()
        registered_at = time.time()
        cursor.execute("INSERT INTO queue (name, phone_number, registered_at, status) VALUES (?, ?, ?, ?)",
                       (queue_data.name, queue_data.phone_number, registered_at, "waiting"))
        conn.commit()
        last_id = cursor.lastrowid
        await manager.broadcast(conn)

        return QueueEntry(id=last_id, name=queue_data.name, phone_number=queue_data.phone_number,
                          registered_at=registered_at, status="waiting")
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="이미 등록된 전화번호입니다.")


@app.post("/api/v1/queue/call-next")
async def call_next_user(conn: sqlite3.Connection = Depends(get_db_conn)):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, phone_number FROM queue WHERE status = 'waiting' ORDER BY registered_at ASC LIMIT 1")
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail="대기 중인 사용자가 없습니다.")

    user_id, user_name, phone_number = user["id"], user["name"], user["phone_number"]
    cursor.execute("UPDATE queue SET status = ? WHERE id = ?", ("called", user_id))
    conn.commit()

    await manager.broadcast(conn)

    return {"called_user_name": user_name, "phone_number": phone_number}


@app.post("/api/v1/queue/call-specific/{phone_number}")
async def call_specific_user(phone_number: str, conn: sqlite3.Connection = Depends(get_db_conn)):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM queue WHERE phone_number = ?", (phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{phone_number}'에 해당하는 사용자가 없습니다.")

    user_id, user_name = user["id"], user["name"]
    cursor.execute("UPDATE queue SET status = ? WHERE id = ?", ("called", user_id))
    conn.commit()

    await manager.broadcast(conn)

    return {"called_user_name": user_name, "phone_number": phone_number}
# --- /api/v1/queue/complete 엔드포인트 수정 ---
@app.post("/api/v1/queue/complete")
async def complete_user(complete_data: CompleteData, conn: sqlite3.Connection = Depends(get_db_conn)):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM queue WHERE phone_number = ?", (complete_data.phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{complete_data.phone_number}'에 해당하는 사용자가 없습니다.")

    user_name = user["name"]
    cursor.execute("DELETE FROM queue WHERE phone_number = ?", (complete_data.phone_number,))

    # 게임 값 유효성 확인
    game = complete_data.game
    if game not in GAMES:
        raise HTTPException(status_code=400, detail=f"유효하지 않은 게임입니다. 허용된 값: {GAMES}")

    # 이름+게임+전화번호 기준으로 점수 저장 (중복 이름 문제 해결)
    cursor.execute(
        """
        INSERT OR REPLACE INTO rankings (name, phone_number, game, score)
        VALUES (?, ?, ?, ?)
        """,
        (user_name, complete_data.phone_number, game, complete_data.score)
    )
    conn.commit()

    await manager.broadcast(conn)

    return {"message": f"'{user_name}'님의 서비스가 완료되고, 게임({game}) 점수({complete_data.score})가 반영되었습니다."}


@app.post("/api/v1/queue/cancel")
async def cancel_user(queue_data: QueueData, conn: sqlite3.Connection = Depends(get_db_conn)):
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM queue WHERE phone_number = ?", (queue_data.phone_number,))
    user = cursor.fetchone()

    if not user:
        raise HTTPException(status_code=404, detail=f"전화번호 '{queue_data.phone_number}'에 해당하는 사용자가 없습니다.")

    user_name = user["name"]
    cursor.execute("DELETE FROM queue WHERE phone_number = ?", (queue_data.phone_number,))
    conn.commit()

    await manager.broadcast(conn)

    return {"message": f"'{user_name}'님의 대기열 등록이 취소되었습니다."}


@app.websocket("/api/v1/queue/ws")
async def websocket_endpoint(websocket: WebSocket, conn: sqlite3.Connection = Depends(get_db_conn)):
    mode = await manager.connect(websocket)
    try:
        # send initial payload according to mode
        initial_data = get_queue_data(conn)
        if mode == "queue":
            await websocket.send_text(json.dumps({"queue_list": initial_data.get("queue_list", [])}))
        else:
            await websocket.send_text(json.dumps(initial_data))
        while True:
            # keep the socket open; we don't expect incoming messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket Error: {e}")


@app.get("/api/v1/rankings/all", response_model=List[FullRankingEntry])
async def get_all_rankings(conn: sqlite3.Connection = Depends(get_db_conn)):
    cursor = conn.cursor()
    cursor.execute("SELECT name, phone_number, game, score FROM rankings ORDER BY game, score DESC")
    ranking_rows = cursor.fetchall()
    return [FullRankingEntry(**dict(row)) for row in ranking_rows]



@app.delete("/api/v1/rankings")
async def delete_ranking_entry(entry: FullRankingEntry, conn: sqlite3.Connection = Depends(get_db_conn)):
    """
    특정 사용자의 특정 게임 랭킹 기록을 삭제합니다.
    """
    cursor = conn.cursor()
    # 항목이 존재하는지 먼저 확인
    cursor.execute("SELECT 1 FROM rankings WHERE name = ? AND game = ? AND score = ?", (entry.name, entry.game, entry.score))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="삭제할 랭킹 항목을 찾을 수 없습니다.")

    cursor.execute("DELETE FROM rankings WHERE name = ? AND game = ? AND score = ?", (entry.name, entry.game, entry.score))
    conn.commit()

    # 랭킹이 변경되었으므로 모든 클라이언트에 브로드캐스트
    await manager.broadcast(conn)

    return {"message": f"'{entry.name}'님의 '{entry.game}' 랭킹 기록(점수: {entry.score})이 삭제되었습니다."}


# 이전 /api/v1/queue/all 엔드포인트는 삭제합니다.
# 'completed' 상태는 queue 테이블에 존재하지 않기 때문입니다.
