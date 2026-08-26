import logging
import sys
import uuid

_run_id = "-"


class _RunIdFilter(logging.Filter):
    def filter(self, record):
        record.run_id = _run_id
        return True


def configure_logging(level="INFO"):
    fmt = logging.Formatter("%(asctime)s %(levelname)s run_id=%(run_id)s %(name)s: %(message)s")
    run_id_filter = _RunIdFilter()

    # File handler — full detail goes to run.log
    file_handler = logging.FileHandler("run.log", encoding="utf-8")
    file_handler.setFormatter(fmt)
    file_handler.addFilter(run_id_filter)
    file_handler.setLevel(level)

    # Console handler — only WARNING and above so the terminal stays clean
    # console_handler = logging.StreamHandler(sys.stdout)  # original: logs everything to console
    # console_handler.setFormatter(fmt)
    # console_handler.addFilter(run_id_filter)
    # console_handler.setLevel(level)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(fmt)
    console_handler.addFilter(run_id_filter)
    console_handler.setLevel(logging.WARNING)

    root = logging.getLogger()
    root.handlers = [file_handler, console_handler]
    root.setLevel(level)


def new_run_id():
    """Generate a run id and use it for every log line until the next call."""
    global _run_id
    _run_id = uuid.uuid4().hex[:12]
    return _run_id
