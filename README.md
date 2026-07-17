# 草莓软酱

Live2D 金融助手，含前端页面和 FastAPI 后端。

## 结构
- frontend/ - 前端页面（index.html）
- backend/ - FastAPI 登录/聊天记录后端

## 后端运行
cd backend && pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 3005
