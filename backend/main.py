import json
import os
import hashlib
import secrets
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DATA_DIR = Path("/var/www/portal/temp/strawberry-data")
USERS_FILE = DATA_DIR / "users.json"
HISTORY_DIR = DATA_DIR / "chat_history"
TOKENS_FILE = DATA_DIR / "tokens.json"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        USERS_FILE.write_text("{}")
    if not TOKENS_FILE.exists():
        TOKENS_FILE.write_text("{}")

def load_json(path):
    return json.loads(path.read_text())

def save_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def get_user_from_token(token: str) -> str:
    tokens = load_json(TOKENS_FILE)
    entry = tokens.get(token)
    if not entry:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    if time.time() > entry["expires"]:
        tokens.pop(token)
        save_json(TOKENS_FILE, tokens)
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    return entry["username"]


class AuthRequest(BaseModel):
    username: str
    password: str

class SaveHistoryRequest(BaseModel):
    messages: list
    summary: str = ""

class UpdateSummaryRequest(BaseModel):
    summary: str


@app.get("/health")
def health():
    ensure_dirs()
    return {"status": "ok"}


@app.post("/register")
def register(req: AuthRequest):
    ensure_dirs()
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")
    if len(req.username) < 2 or len(req.username) > 20:
        raise HTTPException(status_code=400, detail="用户名长度 2-20 位")
    if len(req.password) < 4:
        raise HTTPException(status_code=400, detail="密码至少 4 位")
    users = load_json(USERS_FILE)
    if req.username in users:
        raise HTTPException(status_code=409, detail="用户名已存在")
    users[req.username] = {
        "password": hash_password(req.password),
        "created_at": int(time.time()),
        "summary": "",
    }
    save_json(USERS_FILE, users)
    return {"message": "注册成功"}


@app.post("/login")
def login(req: AuthRequest):
    ensure_dirs()
    users = load_json(USERS_FILE)
    user = users.get(req.username)
    if not user or user["password"] != hash_password(req.password):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = secrets.token_hex(32)
    tokens = load_json(TOKENS_FILE)
    # 清理该用户旧 token
    tokens = {k: v for k, v in tokens.items() if v["username"] != req.username}
    tokens[token] = {
        "username": req.username,
        "expires": int(time.time()) + 30 * 24 * 3600,  # 30天
    }
    save_json(TOKENS_FILE, tokens)
    return {"token": token, "username": req.username}


@app.get("/me")
def get_me(authorization: str = Header(None)):
    ensure_dirs()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:]
    username = get_user_from_token(token)
    users = load_json(USERS_FILE)
    user = users[username]
    history_file = HISTORY_DIR / f"{username}.json"
    recent = []
    if history_file.exists():
        all_history = json.loads(history_file.read_text())
        recent = all_history[-40:] if len(all_history) > 40 else all_history
    return {
        "username": username,
        "summary": user.get("summary", ""),
        "recent_messages": recent,
    }


@app.post("/save_history")
def save_history(req: SaveHistoryRequest, authorization: str = Header(None)):
    ensure_dirs()
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录")
    token = authorization[7:]
    username = get_user_from_token(token)
    history_file = HISTORY_DIR / f"{username}.json"
    existing = json.loads(history_file.read_text()) if history_file.exists() else []
    existing.extend(req.messages)
    # 最多保留 200 条
    if len(existing) > 200:
        existing = existing[-200:]
    history_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    if req.summary:
        users = load_json(USERS_FILE)
        users[username]["summary"] = req.summary
        save_json(USERS_FILE, users)
    return {"message": "已保存"}


@app.post("/logout")
def logout(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return {"message": "ok"}
    token = authorization[7:]
    tokens = load_json(TOKENS_FILE)
    tokens.pop(token, None)
    save_json(TOKENS_FILE, tokens)
    return {"message": "已退出"}


import urllib.request
import urllib.parse

@app.get("/stock/search")
def stock_search(key: str):
    """代理新浪股票搜索，内网无法直接访问新浪"""
    try:
        url = 'https://suggest3.sinajs.cn/suggest/type=11,12&key=' + urllib.parse.quote(key)
        req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"data": resp.read().decode('gbk', errors='replace')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stock/quote")
def stock_quote(codes: str):
    """代理新浪实时行情，如 codes=sh600519,sz002262"""
    try:
        url = 'https://hq.sinajs.cn/list=' + codes
        req = urllib.request.Request(url, headers={'Referer': 'https://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            return {"data": resp.read().decode('gbk', errors='replace')}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
