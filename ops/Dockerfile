FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10002 --no-create-home memory
COPY python /app/python
COPY schemas /app/schemas
COPY ops/entrypoint.py /app/entrypoint.py
USER 10002:10002
ENTRYPOINT ["python", "/app/entrypoint.py"]
