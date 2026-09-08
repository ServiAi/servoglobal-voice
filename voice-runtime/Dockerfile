FROM python:3.11-slim

WORKDIR /app
RUN useradd --create-home --uid 10001 runtime
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
USER runtime
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/')" || exit 1
CMD ["python", "-m", "serviglobal_voice_runtime.main", "start"]
