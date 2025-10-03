# 실시간 대기열 관리 시스템 (FastAPI & WebSocket)

이 프로젝트는 FastAPI를 사용하여 실시간으로 대기열 및 랭킹을 관리하는 백엔드 시스템입니다. WebSocket을 통해 모든 클라이언트에 최신 상태를 즉시 전송하며, SQLite3 데이터베이스를 사용하여 데이터를 저장합니다.

## 📁 프로젝트 구조
```
├── main.py
├── queue.db  # 서버 실행 시 자동 생성
└── clients/
├── admin.html
├── display.html
└── cancel.html
```

## 🚀 실행 방법

### 1. 환경 설정
필요한 Python 라이브러리를 설치합니다. `sqlite3`는 Python에 내장되어 있습니다.

```bash
pip install fastapi uvicorn
```
### 데이터베이스 초기화
개발 중 데이터베이스를 초기화하고 싶을 때는 `uvicorn` 서버를 종료한 후 다음 스크립트를 실행합니다.

```bash
python init_db.py
```