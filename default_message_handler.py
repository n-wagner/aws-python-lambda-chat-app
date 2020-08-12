import logging
from chat_utilities import _build_response

logger = logging.getLogger("connection_handler")
logger.setLevel(logging.DEBUG)


def default_message (event, context):
  """
  Return an error when unexpected WebSocket event occurs
  """
  error_message = "Unexpected WebSocket event"
  logger.info(error_message)
  return _build_response(400, error_message)