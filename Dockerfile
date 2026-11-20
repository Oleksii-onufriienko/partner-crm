FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn
COPY crm ./crm
COPY wsgi.py run.py seed_demo.py ./
ENV CRM_INSTANCE=/data \
    CRM_SECURE_COOKIES=1 \
    CRM_BEHIND_PROXY=1
VOLUME ["/data"]
EXPOSE 8000
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:8000", "wsgi:app"]
