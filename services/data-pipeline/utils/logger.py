import logging
from pathlib import Path

_LOG_DIR = Path("logs")


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    # Defer mkdir until first logger is actually created (not at import time).
    _LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    info_handler = logging.FileHandler(_LOG_DIR / "processing.log")
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)

    error_handler = logging.FileHandler(_LOG_DIR / "errors.log")
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    logger.addHandler(info_handler)
    logger.addHandler(error_handler)
    logger.propagate = False

    return logger
