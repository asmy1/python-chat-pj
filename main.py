import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from pydantic import BaseModel
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_google_community.search import GoogleSearchAPIWrapper
from langchain.tools import BaseTool

from langchain_openai.chat_models import ChatOpenAI
from dotenv import load_dotenv
import requests

load_dotenv()

# NewsAPI用変数
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")
NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"

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

# 日本語を英語に翻訳
def translate_to_english(text: str) -> str:
    """
    日本語を英語に翻訳して返す
    """
    prompt = f"""
以下の日本語を**余計な説明なしで英語に翻訳してください**。
出力は翻訳文のみとしてください。

日本語: {text}
"""
    response = chat_model.invoke(prompt)
    return response.content.strip()


def run_chat_mode(session_id: str, user_input: str):
    """💬 通常の会話モード"""
    response = chat_runnable.invoke(
        {"input": user_input},
        config={"configurable": {"session_id": session_id}}
    )
    return response.content


# --- ニュース検索 ---
def search_news(query: str):
    print("query: ", query)
    params = {
        "q": query,       
        "sortBy": "relevancy",               # ソート順
        "apiKey": NEWSAPI_KEY,
    }
    response = requests.get(NEWSAPI_ENDPOINT, params=params)
    # レスポンスを出力
    if response.status_code == 200:
        articles = response.json().get("articles", [])
        print(articles)
        for i, article in enumerate(articles):
            print(f"{i + 1}. {article['title']} - {article['source']['name']}")
        return articles
    else:
        print(f"Error: {response.status_code} - {response.text}")

def format_articles(articles):
    """
    NewsAPIから返ってきた articles を UI 向けに整形（タイトル＋リンクのみ）
    
    Parameters
    ----------
    articles : list[dict]
        NewsAPI の記事情報
    
    Returns
    -------
    str
        Markdown形式で整形された記事リスト
    """
    if not articles:
        return "該当するニュースはありません。"

    formatted = []
    for i, article in enumerate(articles, start=1):
        title = article.get("title", "タイトルなし")
        url = article.get("url", "")
        # Markdown形式でリンクを作成
        formatted.append(f"{i}. [{title}]({url})")

    return "\n".join(formatted)

# --- ニュース検索モード関数 ---
def run_news_mode(session_id: str, user_input: str):
    memory = get_session_history(session_id)
    translated_query = translate_to_english(user_input)
    print("translate:", translated_query)
    articles = search_news(translated_query)
    format_result = format_articles(articles)
    memory.add_user_message(user_input)
    memory.add_ai_message(format_result)

    return f"📰 ニュース検索結果の要約:\n{format_result}"

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
    prompt = f"""
次の文章がどのモードか判定してください。
「ニュース関連の検索」なら news、
「一般的な検索」なら search、
「会話・雑談」なら chat を返してください。
文章: 「{user_input}」
"""
    # ChatOpenAIで判定
    response = chat_model.invoke(prompt)
    content = response.content.lower()
    print(f"content: {content}")

    if "news" in content:
        return "news"
    elif "search" in content:
        return "search"
    else:
        return "chat"

class ChatRequest(BaseModel):
    message: str
    mode: str | None = None  # "chat" or "search" or "news" or None（自動判定）

@app.post("/")
def chat(req: ChatRequest):
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
    if mode == "news":
        answer = run_news_mode(session_id, user_input)
    elif mode == "search":
        answer = run_search_mode(session_id, user_input)
    else:
        answer = run_chat_mode(user_input, user_input)

    return {"mode": mode, "response": answer}

