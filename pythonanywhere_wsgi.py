"""WSGI-файл для PythonAnywhere.

Скопируйте содержимое в файл /var/www/<логин>_eu_pythonanywhere_com_wsgi.py
(вкладка Web → ссылка «WSGI configuration file»). Код лежит в ~/partner-crm,
база и секретный ключ — в ~/crm-data (эта папка не затрагивается при обновлении кода).
"""
import os
import sys

HOME = os.path.expanduser("~")
PROJECT = os.path.join(HOME, "partner-crm")
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

os.environ.setdefault("CRM_INSTANCE", os.path.join(HOME, "crm-data"))
os.environ.setdefault("CRM_SECURE_COOKIES", "1")   # сайт открыт по https
os.environ.setdefault("CRM_BEHIND_PROXY", "1")     # перед приложением прокси PythonAnywhere

from crm import create_app  # noqa: E402

application = create_app()
