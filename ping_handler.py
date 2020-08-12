import os
import logging
from chat_utilities import _build_response

logger = logging.getLogger("ping_handler")
logger.setLevel(logging.DEBUG)


def ping (event, context):
    """
    Basic connection check
    """
    logger.info("Ping requested.")
    logger.debug("OS Environ: {}".format(os.environ))
    return _build_response(200, "PONG!")
