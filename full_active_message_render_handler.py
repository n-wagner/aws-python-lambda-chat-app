import jinja2
import logging
import json
import boto3
import base64
from chat_utilities import _build_response, _fetch_body, S3Loader

logger = logging.getLogger("full_active_message_render_handler")
logger.setLevel(logging.DEBUG)


def full_active_message_render (event, context):
  """
  Render active message pane - expects event to have body with current user and list of message groupings
  """
  logger.debug("Event: {} type: {}".format(event, type(event)))
  logger.debug("Context: {}".format(context))
  body = event["body"]
  logger.debug("body: {}".format(body))
  for attribute in ["username", "all_messages"]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      return _build_response(400, error_message)
  username = body["username"]
  all_messages = body["all_messages"]
  env = jinja2.Environment(
    loader=S3Loader('chat-application-upload-bucket-11097', logger),
    autoescape=jinja2.select_autoescape(['html', 'xml'])
  )
  template = env.get_template('jinja_message_template.html')
  logger.debug("template: {}".format(template))
  done = template.render(current_user=username, all_messages=all_messages)
  logger.debug("template_done: '{}'".format(done))
  logger.debug("template_type: {}".format(type(done)))
  # encoded_payload = base64.b64encode(done.encode('utf-8')).decode('utf-8')
  # logger.debug("encoded: '{}' type: {}".format(encoded_payload, type(encoded_payload)))
  return _build_response(200, done)
