"""Small, rotating operational log; never persist audio, text or credentials."""
import logging
from logging.handlers import RotatingFileHandler
import os

logger = logging.getLogger("dita_eu")
logger.addHandler(logging.NullHandler())
logger.propagate = False


def configure_runtime_logging():
    for handler in logger.handlers:
        if isinstance(handler, RotatingFileHandler):
            return handler.baseFilename
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "Dita-eu", "logs", "runtime.log")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=3, encoding="utf-8")
    except OSError:
        return None
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(message)s"))
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return path
