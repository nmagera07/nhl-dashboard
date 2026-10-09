FROM python:3.13-slim
# Links the GHCR package to the repo (and makes it public with it).
LABEL org.opencontainers.image.source=https://github.com/nmagera07/nhl-dashboard

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser app ./app

# Set by the deploy workflow and reported by GET /health, so the deploy can
# verify production is running this exact commit.
ARG GIT_SHA=unknown
ENV GIT_SHA=$GIT_SHA

USER appuser
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
