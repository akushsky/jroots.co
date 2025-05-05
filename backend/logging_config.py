import logging
import logging.config
from logging import Logger

from colorlog import ColoredFormatter
from pythonjsonlogger.json import JsonFormatter

from trace_context import get_trace_id


class TraceJsonFormatter(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        # Inject trace_id into the record dynamically
        log_record['trace_id'] = get_trace_id()

class TraceColoredFormatter(ColoredFormatter):
    def format(self, record):
        # Inject trace_id into the record dynamically
        record.trace_id = get_trace_id()
        return super().format(record)

def generate_logging_config():
    handlers = {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "colored",
            "level": "INFO",
        }
    }

    formatters = {
        "colored": {
            "()": "logging_config.TraceColoredFormatter",
            "format": "%(log_color)s%(asctime)s [%(levelname)s] %(trace_id)s %(message)s",
            "log_colors": {
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
        },
    }

    # Try JSON formatter if available
    try:
        import pythonjsonlogger
        formatters["json"] = {
            "()": "logging_config.TraceJsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(trace_id)s %(message)s",
        }
    except ImportError:
        pass

    # Try Loki handler if available
    try:
        from loki_logger import LokiHandler

        handlers.clear()  # Clear existing handlers to avoid conflicts
        handlers["loki"] = {
            "class": "loki_logger.LokiHandler",
            "level": "INFO",
            "formatter": "json" if "json" in formatters else "colored",
            "url": "http://loki:3100/loki/api/v1/push",
            "tags": {
                "app": "jroots",
                "env": "production",
                "host": "coolify",
                "service": "backend",
                "logger": "jroots"
            },
            "version": "1",
        }
    except ImportError:
        pass

    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "loggers": {
            "uvicorn": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": [],
                "level": "WARNING",
                "propagate": False,
            },
            "fastapi": {
                "handlers": ["console"],
                "level": "INFO",
                "propagate": True,
            },
            "jroots": {
                "handlers": list(handlers.keys()),
                "level": "INFO",
                "propagate": True,
            },
        },
        "root": {
            "level": "INFO",
            "handlers": list(handlers.keys()),
        }
    }

    return config


def setup_logging():
    config = generate_logging_config()
    try:
        logging.config.dictConfig(config)
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logging.warning("Fallback to basic logging due to error: %s", str(e))


def construct_logger(name: str) -> Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    return logger
