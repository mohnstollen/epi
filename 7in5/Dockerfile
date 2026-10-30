FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 TZ=Europe/Berlin
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY infotafel ./infotafel
EXPOSE 8080
HEALTHCHECK --interval=2m --timeout=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/status.json', timeout=5)"
CMD ["python", "-m", "infotafel", "serve", "--config", "/config/config.toml", "--port", "8080"]
