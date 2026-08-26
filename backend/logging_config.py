"""
Shared logging setup for the NHL Stats Dashboard backend.

Used by both the 5 standalone ingestion scripts (run via an Azure Container Apps Job
`nhl-standings-ingest` for the daily jobs, or manually for the weekly/one-off scripts) and
api.py (runs inside an Azure Container App, where stdout/stderr is already
captured by Azure's own logging).

Usage:
    from logging_config import setup_logging
    logger = setup_logging(__name__)                  # ingestion scripts: console + rotating file
    logger = setup_logging(__name__, log_to_file=False)  # api.py: console only
"""

import logging
import logging.handlers
import os

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")

# 5 MB per file, keep 5 backups -- plenty of history for a daily scheduled
# task without letting log files grow unbounded.
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def setup_logging(name, log_to_file=True, level=logging.INFO):
    """
    Configure and return a logger.

    - Always attaches a console (stream) handler.
    - When log_to_file is True (the default, used by the ingestion scripts),
      also attaches a RotatingFileHandler writing to backend/logs/<name>.log
      so a 6am scheduled run leaves a durable record even though nothing is
      watching the console.
    - api.py runs in an ephemeral Azure Container App instance where a local
      log file would just be lost on restart/redeploy, and Azure already
      captures stdout/stderr -- so it should call this with
      log_to_file=False and rely on the console handler only.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid attaching duplicate handlers if setup_logging(name) is called
    # more than once for the same logger name (e.g. reload in development).
    if logger.handlers:
        return logger

    formatter = logging.Formatter(LOG_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_to_file:
        os.makedirs(LOGS_DIR, exist_ok=True)
        log_file = os.path.join(LOGS_DIR, f"{name}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger
