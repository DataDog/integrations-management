from logging import getLogger

log = getLogger("installer")


def log_header(message: str):
    """Log a formatted header message."""
    separator = "=" * 70
    header = "\n".join(["", separator, message, separator, ""])
    log.info(header)
