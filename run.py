"""Запуск CRM.  python run.py  → http://127.0.0.1:8000

Переменные окружения (необязательно):
  CRM_HOST=0.0.0.0        слушать все интерфейсы (для доступа из сети)
  CRM_PORT=8000           порт
  CRM_DB=путь/к/crm.sqlite3
  CRM_SECURE_COOKIES=1    если сайт открыт по https
  CRM_BEHIND_PROXY=1      если перед приложением стоит nginx / Caddy / Cloudflare Tunnel
"""
import os

from crm import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("CRM_HOST", "127.0.0.1")
    port = int(os.environ.get("CRM_PORT", "8000"))
    try:
        from waitress import serve
        print(f"Partner CRM: http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port}")
        serve(app, host=host, port=port, threads=8)
    except ImportError:
        print("waitress не установлен — запускаю встроенный сервер Flask (только для пробы).")
        app.run(host=host, port=port)
