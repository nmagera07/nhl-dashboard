# Dockerfile for the NHL Stats Dashboard API
# Built and run by Azure Container Apps (via ACR cloud build - no local Docker needed)

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user -- api.py never writes to the filesystem at
# runtime (log_to_file=False, see logging_config.py), so this is a plain
# ownership handoff with no permission gaps to work around.
RUN useradd --create-home --shell /bin/bash appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]