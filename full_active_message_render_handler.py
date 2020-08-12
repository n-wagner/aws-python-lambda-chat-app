import logging
import jinja2
from chat_utilities import _build_response, S3Loader

logger = logging.getLogger("full_active_message_render_handler")
logger.setLevel(logging.DEBUG)

def full_active_message_render(event, context):
  """
  Render active message pane - expects event to have body with current user and list of message groupings
  """
  logger.debug("Event: {} type: {}", event, type(event))
  logger.debug("Context: {}", context)
  body = event["body"]
  logger.debug("body: {}", body)
  for attribute in ["username", "all_messages"]:
    if attribute not in body:
      error_message = "Improper message format: `{}' missing from message JSON".format(attribute)
      logger.debug(error_message)
      return _build_response(400, error_message)
  username = body["username"]
  all_messages = body["all_messages"]
  env = jinja2.Environment(
    loader=S3Loader('chat-application-upload-bucket-11097', logger),
    autoescape=jinja2.select_autoescape(['html', 'xml'])
  )
  template = env.get_template('jinja_message_template.html.j2')
  logger.debug("template: {}", template)
  done = template.render(current_user=username, all_messages=all_messages)
  logger.debug("template_done: '{}', template_type: {}", done, type(done))
  # encoded_payload = base64.b64encode(done.encode('utf-8')).decode('utf-8')
  # logger.debug("encoded: '{}' type: {}".format(encoded_payload, type(encoded_payload)))
  return _build_response(200, done)
