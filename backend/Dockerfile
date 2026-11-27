FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Ho_Chi_Minh

WORKDIR /app
COPY pyproject.toml ./
COPY xs247 ./xs247
RUN pip install --no-cache-dir . \
 && useradd --create-home --uid 1000 app \
 && mkdir -p /data/raw && chown -R app:app /data
COPY fixtures ./fixtures

USER app
EXPOSE 8000
CMD ["uvicorn", "xs247.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
