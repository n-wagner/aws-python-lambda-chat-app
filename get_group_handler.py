import os
import json
import logging
from datetime import datetime
import boto3
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("get_group_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "getGroup"

def get_group(event, context):
  """
  Return a selected group
  """
  logger.info("Entering a group")
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}", connectionID)

  # Validate the connection is logged in

  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  response = connections_table.query(
    ProjectionExpression=definitions.Connections.USERNAME,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Connections.CONNECTION_ID).eq(connectionID)
  )
  logger.debug("response: {}", response)
  items = response.get("Items", [])
  logger.debug("items: {}", items)
  if len(items) >= 0:
    item = items[0]
  else:
    logger.error("user password query returned not even an empty set items: {}", items)
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Server error"), event)
    return _build_response(500, "Server error")
  if definitions.Connections.USERNAME not in item:
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Not logged in"), event)
    return _build_response(401, "Not logged in")

  username = item[definitions.Connections.USERNAME]

  default_fetch = 20  # Default number of messages to fetch

  body = _fetch_body(event, logger)
  for attribute in [definitions.Groups.GROUP_ID]:
    if attribute not in body:
      error_message = "Improper message format: `{}' missing from message JSON".format(attribute)
      logger.debug(error_message)
      _send_to_connection(connectionID, _build_response_detailed(400, action, error_message), event)
      return _build_response(400, error_message)

  group = body[definitions.Groups.GROUP_ID]

  # # Validate the connection is logged in

  # connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  # response = connections_table.query(
  #   ProjectionExpression=definitions.Connections.USERNAME,
  #   KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Connections.CONNECTION_ID).eq(connectionID)
  # )
  # logger.debug("response: {}".format(response))
  # items = response.get("Items", [])
  # logger.debug("items: {}".format(items))
  # if (len(items) > 0):
  #   item = items[0]
  # else:
  #   logger.error("user password query returned not even an empty set items: {}".format(items))
  #   _send_to_connection(connectionID, _build_response_detailed(500, action, "Server error"), event)
  #   return _build_response(500, "Server error")
  # if definitions.Connections.USERNAME not in item:
  #   _send_to_connection(connectionID, _build_response_detailed(401, action, "Not logged in"), event)
  #   return _build_response(401, "Not logged in")

  # username = item[definitions.Connections.USERNAME]

  # Validate the user is a member of the group

  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  response = groups_table.query(
    # ProjectionExpression="{}, {}".format(definitions.Groups.USERNAME, definitions.Groups.NICKNAME),
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Groups.GROUP_ID).eq(group)
  )
  items = response.get("Items", [])
  logger.debug("items: {}", str(items))
  ok = False
  # current_user_exclusion_list = []
  # current_user_left_timestamp = -1
  for item in items:
    if item[definitions.Groups.USERNAME] == username:
      ok = True
      current_user_exclusion_list = item[definitions.Groups.EXCLUSION_LIST] if definitions.Groups.EXCLUSION_LIST in item else []
      current_user_left = bool(current_user_exclusion_list) and len(current_user_exclusion_list[-1]) == 1
      # Note if the current user has left the group
      # if definitions.Groups.EXCLUSION_LIST in item and len(item[definitions.Groups.EXCLUSION_LIST][-1]) == 1:
        # current_user_left = True
        # current_user_left_timestamp = item[definitions.Groups.EXCLUSION_LIST]
      break
  if not ok:
    _send_to_connection(connectionID, _build_response_detailed(403, action, "Not a member of group"), event)
    return _build_response(403, "Not a member of group")

  logger.debug("current_user_left: {} current_user_exclusion_list: {} ".format(current_user_left, current_user_exclusion_list))

  # Group table info to get the group nickname & list of users

  nickname = items[0][definitions.Groups.NICKNAME]
  current_group_users = [item[definitions.Groups.USERNAME] for item in items if not (definitions.Groups.EXCLUSION_LIST in item and len(item[definitions.Groups.EXCLUSION_LIST][-1]) == 1)]
  # current_user_left = username not in current_group_users
    # definitions.Groups.LEFT: item[definitions.Groups.LEFT] if definitions.Groups.LEFT in item else False

  logger.debug("nickname: {} current_group_users: {}", nickname, current_group_users)

  logger.debug("group: {}", group)
  messages_table = dynamodb.Table(definitions.Messages.TABLE_NAME)
  local_name_1 = ":group_id"
  local_name_2_template = ":timestmp{}_{}"
  # local_name_2 = ":timestmp"
  if current_user_left:
    expression_attribute_values = {
      definitions.Messages.HASH_KEY: local_name_1
    }
    key_condition_expression = [["{} = {} and (".format(definitions.Messages.HASH_KEY, local_name_1)]]
    for i, exclusion_item in enumerate(current_user_exclusion_list):
      exclusion_pair = []
      temp_local_name_2 = local_name_2_template.format(i, 0)
      message = "{} <= {}".format(definitions.Messages.RANGE_KEY, temp_local_name_2)
      expression_attribute_values[temp_local_name_2] = exclusion_item[0]
      if len(exclusion_item) > 1:
        exclusion_pair.append(message)
        temp_local_name_2 = local_name_2_template.format(i, 1)
        exclusion_pair.append("{} >= {}".format(definitions.Messages.RANGE_KEY, temp_local_name_2))
        expression_attribute_values[temp_local_name_2] = exclusion_item[1]
      else:
        message += ")"
        exclusion_pair.append(message)

    logger.debug("KeyConditionExpression before join: {}", key_condition_expression)
    key_condition_expression = " and ".join(" or ".join(item) for item in key_condition_expression)
    logger.debug("KeyConditionExpression after join: {}", key_condition_expression)
    logger.debug("ExpressionAttributeValues: {}", expression_attribute_values)
    response = messages_table.query(
      KeyConditionExpression=key_condition_expression,
      ExpressionAttributeValues=expression_attribute_values,
      Limit=default_fetch,
      ScanIndexForward=False
    )
    # items = response.get("Items", [])
    # logger.debug("items: {}".format(str(items)))
    # if len(items) > default_fetch:
    #   items = items[-default_fetch:]
    # logger.debug("items: {}".format(str(items)))
  else:
    response = messages_table.query(
      KeyConditionExpression="{} = {}".format(definitions.Messages.HASH_KEY, local_name_1),
      ExpressionAttributeValues={
        local_name_1: group
      },
      Limit=default_fetch,
      ScanIndexForward=False
    )
  items = response.get("Items", [])
  logger.debug("items: {}", str(items))
  # How many new messages were actually taken
  messages = [
    {
      definitions.Messages.USERNAME: item[definitions.Messages.USERNAME] if definitions.Messages.USERNAME in item else None,
      definitions.Messages.CONTENT: item[definitions.Messages.CONTENT],
      definitions.Messages.TIMESTAMP: datetime.fromtimestamp(item[definitions.Messages.TIMESTAMP] // 1000000000).strftime('%m/%d/%Y %H:%M'),
      #definitions.Messages.INIT: x[definitions.Messages.INIT] if definitions.Messages.INIT in x else False
    } for item in items
  ]
  messages.reverse()
  memo_username = None
  all_messages = []
  temp_list = []
  # init_set = False
  for message in messages:
    if memo_username is None:
      memo_username = message[definitions.Messages.USERNAME]
      if temp_list:
        all_messages.append(temp_list[:])
        temp_list.clear()
      # if message[definitions.Messages.INIT] == True:
      #   init_set = True
    elif memo_username != message[definitions.Messages.USERNAME]:
      memo_username = message[definitions.Messages.USERNAME]
      all_messages.append(temp_list[:])
      temp_list.clear()
      # if init_set == True:
      #   init_set = False
    temp_list.append(message)
  if temp_list:
    all_messages.append(temp_list)

  logger.debug("Messages: {}", str(messages))
  logger.debug("All Messages: {}", str(all_messages))
  # Send data to requesting client (render)
  params = {
    "body": {
      "left": current_user_left,
      "nickname": nickname,
      "group_users": current_group_users,
      "username": username,
      "all_messages": all_messages,
      "groupID": group
    }
  }
  lambda_client = boto3.client("lambda")
  invoke_response = lambda_client.invoke(
    FunctionName="chat-application-dev-activePaneRender",
    InvocationType="RequestResponse",
    Payload=json.dumps(params)
  )
  payload = invoke_response['Payload'].read().decode()
  logger.debug("Payload: '{}' type: {}", payload, type(payload))
  payload_dict = json.loads(payload)
  logger.debug("Payload_dict: '{}' type: {}", payload_dict, type(payload_dict))
  body = {
    "group": group,
    "html": payload_dict["body"]
  }
  _send_to_connection(connectionID, _build_response_detailed(200, action, body), event)
  return _build_response(200, "Sent {} messages".format(len(messages)))