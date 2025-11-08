from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai.chat_models import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# 会話履歴のストア
store = {}

# セッションIDごとの会話履歴の取得
def get_session_history(session_id: str) -> BaseChatMessageHistory:
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

# プロンプトテンプレートで会話履歴を追加
prompt_template = ChatPromptTemplate.from_messages(
    [
        MessagesPlaceholder(variable_name="history"),
        ("human", "{input}"),
    ]
)

# 応答生成モデル（例としてchat_model）
chat_model = ChatOpenAI(model="gpt-4o-mini")

# Runnableの準備
runnable = prompt_template | chat_model

# RunnableをRunnableWithMessageHistoryでラップ
runnable_with_history = RunnableWithMessageHistory(
    runnable=runnable,
    get_session_history=get_session_history,
    input_messages_key="input",
    history_messages_key="history"
)
# 実際の応答生成の例
def chat_with_bot(session_id: str, req:str):
    count = 0
    while True:
        print("---")
        # input_message = input(f"[{count}]あなた: ")
        input_message = req
        if input_message.lower() == "終了":
            break

        if input_message.lower() in ["履歴削除"]:
            memory = get_session_history(session_id)
            memory.clear()
            print("履歴削除しました。")
            return "clear"

        # プロンプトテンプレートに基づいて応答を生成
        response = runnable_with_history.invoke(
            {"input": input_message},
            config={"configurable": {"session_id": session_id}}
        )
        
        print(f"AI: {response.content}")
        count += 1
        return response.content

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

class ChatRequest(BaseModel):
    message: str

@app.post("/")
async def chat(req: ChatRequest):
    print(req.message)
    # answer_data = chat_model.invoke(req.message)
    session_id = "example_session"
    ret = chat_with_bot(session_id, req.message)

    return {"response": {ret}}

