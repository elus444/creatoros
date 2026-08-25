FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status == 200 else sys.exit(1)"

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
