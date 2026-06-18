FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/packages

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY packages ./packages
COPY services/api/app ./services/api/app

WORKDIR /app/services/api

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
