FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AQI_HOME=/app

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . \
    && useradd --create-home appuser

# The image ships the data snapshot, the champion from the registry and the latest reports,
# so a deployed container is a complete, versioned release of the pipeline's output.
COPY data ./data
COPY registry ./registry
COPY reports ./reports

ARG GIT_SHA=unknown
ENV GIT_SHA=${GIT_SHA}

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "aqi.serve.app:app", "--host", "0.0.0.0", "--port", "8000"]
