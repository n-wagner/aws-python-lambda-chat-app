import logging
import jinja2
from chat_utilities import _build_response, S3Loader

logger = logging.getLogger("active_pane_render_handler")
logger.setLevel(logging.DEBUG)

def active_pane_render (event, context):
  """
  Render active message pane - expects event to have body with current user and list of message groupings
  """
  logger.debug("Event: {} type: {}", event, type(event))
  logger.debug("Context: {}", context)
  body = event["body"]
  logger.debug("body: {}", body)
  for attribute in ["left", "nickname", "group_users", "username", "all_messages", "groupID"]:
    if attribute not in body:
      error_message = "Improper message format: `{}' missing from message JSON".format(attribute)
      logger.debug(error_message)
      return _build_response(400, error_message)
  left = body["left"]
  nickname = body["nickname"]
  group_users = body["group_users"]
  username = body["username"]
  all_messages = body["all_messages"]
  groupID = body["groupID"]
  env = jinja2.Environment(
    loader=S3Loader('chat-application-upload-bucket-11097', logger),
    autoescape=jinja2.select_autoescape(['html', 'xml'])
  )
  template = env.get_template('jinja_active_pane_template.html.j2')
  logger.debug("template: {}", template)
  done = template.render(
    left=left,
    nickname=nickname,
    group_users=group_users,
    current_user=username,
    all_messages=all_messages,
    groupID=groupID
  )
  logger.debug("template_done: '{}'", done)
  logger.debug("template_type: {}", type(done))
  # encoded_payload = base64.b64encode(done.encode('utf-8')).decode('utf-8')
  # logger.debug("encoded: '{}' type: {}".format(encoded_payload, type(encoded_payload)))
  return _build_response(200, done)
