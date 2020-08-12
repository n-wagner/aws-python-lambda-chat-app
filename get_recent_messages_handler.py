import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("get_recent_message_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb", 
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "getRecentMessages"

def get_recent_messages (event, callback):
  """
  Return the recent N most messages specified by client
  """
  logger.info("Retrieving the N most recent messages")
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}".format(connectionID))

  # Validate the connection is logged in
  
  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  response = connections_table.query(
    ProjectionExpression=definitions.Connections.USERNAME,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Connections.CONNECTION_ID).eq(connectionID)
  )
  logger.debug("response: {}".format(response))
  items = response.get("Items", [])
  logger.debug("items: {}".format(items))
  if (len(items) >= 0):
    item = items[0]
  else:
    logger.error("user password query returned not even an empty set items: {}".format(items))
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Server error"), event)
    return _build_response(500, "Server error")
  if definitions.Connections.USERNAME not in item:
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Not logged in"), event)
    return _build_response(401, "Not logged in")

  username = item[definitions.Connections.USERNAME]

  default_fetch = 10  # Default number of messages to fetch

  body = _fetch_body(event, logger)
  for attribute in [definitions.Messages.GROUP_ID, "count"]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      return _build_response(400, error_message)
  
  group = body[definitions.Messages.GROUP_ID]
  count = body["count"]

  # Validate the user is a member of the group

  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  response = groups_table.query(
    # ProjectionExpression="{}, {}".format(definitions.Groups.USERNAME, definitions.Groups.NICKNAME),
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Groups.GROUP_ID).eq(group)
  )
  items = response.get("Items", [])
  logger.debug("items: {}".format(str(items)))
  ok = False
  # current_user_exclusion_list = []
  # current_user_left_timestamp = -1
  for item in items:
    if item[definitions.Groups.USERNAME] == username:
      ok = True
      current_user_exclusion_list = item[definitions.Groups.EXCLUSION_LIST] if definitions.Groups.EXCLUSION_LIST in item else []
      current_user_left = bool(current_user_exclusion_list) and len(current_user_exclusion_list[-1]) == 1
      # Note if the current user has left the group
      # if definitions.Groups.LEFT in item and item[definitions.Groups.LEFT] == True:
      #   current_user_left = True
      #   current_user_left_timestamp = item[definitions.Groups.LEFT_TIMESTAMP]
      break
  if not ok:
    _send_to_connection(connectionID, _build_response_detailed(403, action, "Not a member of group"), event)
    return _build_response(403, "Not a member of group")

  logger.debug("current_user_left: {} current_user_exclusion_list: {} ".format(current_user_left, current_user_exclusion_list))


  logger.debug("group: {} count: {} count_type: {}".format(group, count, str(type(count))))
  count = int(count)
  message_number = count + default_fetch
  messages_table = dynamodb.Table(definitions.Messages.TABLE_NAME)
  local_name_1 = ":group_id"
  local_name_2_template = ":timestmp{}_{}"
  # local_name_2 = ":timestmp"
  if (current_user_left == True):
    expression_attribute_values = {definitions.Messages.HASH_KEY: local_name_1}
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
    
    logger.debug("KeyConditionExpression before join: {}".format(key_condition_expression))
    key_condition_expression = " and ".join(" or ".join(item) for item in key_condition_expression)
    logger.debug("KeyConditionExpression after join: {}".format(key_condition_expression))
    logger.debug("ExpressionAttributeValues: {}".format(expression_attribute_values))
    response = messages_table.query(
      KeyConditionExpression=key_condition_expression,
      ExpressionAttributeValues=expression_attribute_values,
      Limit=message_number,
      ScanIndexForward=False
    )
    # response = messages_table.scan(
    #   FilterExpression="{} = {} AND {} <= {}".format(
    #     definitions.Messages.HASH_KEY, 
    #     local_name_1,
    #     definitions.Messages.TIMESTAMP,
    #     local_name_2
    #   ),
    #   ExpressionAttributeValues={
    #     local_name_1: group,
    #     local_name_2: current_user_left_timestamp
    #   },
    #   # Limit=message_number,
    #   ScanIndexForward=False
    # )
    # items = response.get("Items", [])
    # logger.debug("items: {}".format(str(items)))
    # if len(items) > message_number:
    #   items = items[-message_number:]
    # logger.debug("items: {}".format(str(items)))
  else:
    response = messages_table.query(
      KeyConditionExpression="{} = {}".format(definitions.Messages.HASH_KEY, local_name_1),
      ExpressionAttributeValues={
        local_name_1: group
      },
      Limit=message_number,
      ScanIndexForward=False
    )
  items = response.get("Items", [])
  logger.debug("items: {}".format(str(items)))
  # How many new messages were actually taken
  item_len = len(items)
  new_messages_count = item_len - count
  logger.debug("item_len: {} new_messages_count: {}".format(item_len, new_messages_count))
  messages = []
  if (new_messages_count > 0):
    # Only get the newest messages
    # TODO Check if these are the newest messages? ScanIndexForward is reverse so these may be the oldest?
    items = items[:new_messages_count]
    logger.debug("New messages from items: {}".format(items))
    messages = [
      {
        definitions.Messages.USERNAME: item[definitions.Messages.USERNAME] if definitions.Messages.USERNAME in item else None,
        definitions.Messages.CONTENT: item[definitions.Messages.CONTENT],
        definitions.Messages.TIMESTAMP: datetime.fromtimestamp(item[definitions.Messages.TIMESTAMP] // 1000000000).strftime('%m/%d/%Y %H:%M'),
        # definitions.Messages.INIT: x[definitions.Messages.INIT] if definitions.Messages.INIT in x else False
      }
    for item in items]
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
      elif memo_username != message[definitions.Messages.USERNAME]:
        memo_username = message[definitions.Messages.USERNAME]
        all_messages.append(temp_list[:])
        temp_list.clear()
        # if init_set == True:
        #   init_set = False
      temp_list.append(message)
    if temp_list:
      all_messages.append(temp_list)
  else:
    logger.debug("No further new messages")
    return _build_response(200, "No further new messages")

  logger.debug("Messages: {}".format(str(messages)))
  logger.debug("All Messages: {}".format(str(all_messages)))

  # Send data to requesting client (render)

  params = {
    "body": {
      "username": username,
      "all_messages": all_messages
    }
  }
  lambda_client = boto3.client("lambda")
  invoke_response = lambda_client.invoke(
    FunctionName="chat-application-dev-fullActiveMessageRender",
    InvocationType="RequestResponse",
    Payload=json.dumps(params)
  )
  payload = invoke_response['Payload'].read().decode()
  logger.debug("Payload: '{}' type: {}".format(payload, type(payload)))
  payload_dict = json.loads(payload)
  logger.debug("Payload_dict: '{}' type: {}".format(payload_dict, type(payload_dict)))
  # body = {
  #   "group": group,
  #   "html": payload_dict["body"]
  # }
  _send_to_connection(connectionID, _build_response_detailed(200, action, payload_dict["body"]), event)
  return _build_response(200, "Sent {}-{} recent block of messages".format(item_len, count))