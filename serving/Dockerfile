FROM python:3.10-slim

WORKDIR /app

# Install dependencies first (layer caching — deps change less often than code)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# Model will be mounted at /models by the init container
RUN mkdir -p /models

# Non-root user for security
RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]