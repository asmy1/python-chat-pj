from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# React の開発サーバー（例: http://localhost:5173）を許可
origins = [
    "http://localhost:5173",  # Vite のデフォルトポート
    "http://localhost:3000",  # CRA の場合
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 許可するオリジン
    allow_credentials=True,
    allow_methods=["*"],    # すべてのHTTPメソッドを許可
    allow_headers=["*"],    # すべてのヘッダーを許可
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

