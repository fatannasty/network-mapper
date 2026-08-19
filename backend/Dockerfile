FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .

EXPOSE 8000

# Production run: no --reload, single process (SQLite backend).
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
