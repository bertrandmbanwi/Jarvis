# JARVIS API server (backend only). macOS-only tools and local voice are not
# available in the container; chat, web/public-data tools, files under /app/data,
# MCP, skills, Telegram and scheduled routines are.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    API_HOST=0.0.0.0 API_PORT=8741

WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

COPY jarvis ./jarvis
COPY skills ./skills

RUN useradd --create-home jarvis && mkdir -p /app/data && chown -R jarvis /app
USER jarvis

EXPOSE 8741
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8741/health/ping', timeout=3)"
CMD ["python", "-m", "jarvis.main", "server"]
