#!/bin/bash
cd /var/www/strawberry-backend
source venv/bin/activate
exec uvicorn main:app --host 127.0.0.1 --port 3005
