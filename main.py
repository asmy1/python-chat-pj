from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_community.search import GoogleSearchAPIWrapper

from langchain_openai.chat_models import ChatOpenAI
import sqlite3
from dotenv import load_dotenv

load_dotenv()

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

# 会話履歴のストア
store = {}

# セッションIDごとの会話履歴の取得
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

# プロンプトテンプレートで会話履歴を追加
chat_prompt  = ChatPromptTemplate.from_messages(
    [
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)

# モデル作成
chat_model = ChatOpenAI(model="gpt-4o-mini")

# チャットRunnable（履歴保存あり）
chat_runnable = RunnableWithMessageHistory(
    runnable = chat_prompt  | chat_model,
    get_session_history=get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)

# Google Search APIの設定
search_tool = GoogleSearchAPIWrapper()


def run_chat_mode(session_id: str, user_input: str):
    """💬 通常の会話モード"""
    response = chat_runnable.invoke(
        {"input": user_input},
        config={"configurable": {"session_id": session_id}}
    )
    return response.content

def run_search_mode(session_id: str, user_input: str) -> str:
    """🌐 Google検索モード"""
    memory = get_session_history(session_id)
    query = user_input
    for kw in ["検索", "調べて", "探して"]:
        query = query.replace(kw, "")
    query = query.strip()
    if not query:
        return "何を検索すればよいのか教えてください。"

    try:
        result = search_tool.run(query)
    except Exception as e:
        return f"検索中にエラーが発生しました: {e}"
    # run_search_mode.search_cache[query] = result

    # 結果が長い場合は要約
    if len(result) > 1500:
        summary = chat_model.invoke(
            f"以下の検索結果をわかりやすく200文字以内に要約してください:\n\n{result}"
        ).content
        result = summary

    memory.add_user_message(user_input)
    memory.add_ai_message(result)
    return f"🔎 **{query}** の検索結果:\n{result}"


# モード自動判定
def detect_mode(user_input: str) -> str:
    prompt = f"次の文章が検索指示か日常会話か判定してください。「検索」なら search、「会話」なら chat を返してください:\n{user_input}"
    response = chat_model.invoke(prompt)
    return "search" if "search" in response.content.lower() else "chat"

class ChatRequest(BaseModel):
    message: str
    mode: str | None = None  # "chat" or "search" or None（自動判定）



@app.post("/")
async def chat(req: ChatRequest):
    print(req.message)
    session_id = "example_session"
    user_input = req.message.strip()

    # モード設定
    mode = req.mode or detect_mode(user_input)
    
    if user_input.lower() == "終了":
        return {"response": "セッションを終了しました。"}

    if user_input.lower() == "履歴削除":
        store.pop(session_id, None)
        return {"response": "履歴を削除しました。"}
    
    # 各モードへルーティング
    if mode == "search":
        answer = run_search_mode(session_id, user_input)
    else:
        answer = run_chat_mode(session_id, user_input)

    return {"mode": mode, "response": answer}

