import logging

_LOGGER_NAME = "airq"


def configure_logging() -> None:
    # Guard against duplicate handlers: `fastapi dev`'s reloader and pytest
    # can both trigger the lifespan startup more than once per process.
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
