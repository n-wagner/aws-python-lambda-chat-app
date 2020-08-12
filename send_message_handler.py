import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("send_message_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "sendMessage"

def send_message(event, context):
  """
  Forward a message to all appropraite clients
  """
  logger.debug("environ var: {} type: {}", os.environ.get('IS_OFFLINE'), type(os.environ.get('IS_OFFLINE')))
  logger.info("Message sent via WebSocket")
  logger.debug("event: {}", str(event))
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}", connectionID)

  # Validate that user is logged in

  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  response = connections_table.query(
    ProjectionExpression=definitions.Connections.USERNAME,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Connections.CONNECTION_ID).eq(connectionID)
  )
  logger.debug("response: {}", response)
  items = response.get("Items", [])
  logger.debug("items: {}", items)
  if len(items) > 0:
    item = items[0]
  else:
    logger.error("user password query returned not even an empty set items: {}", items)
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Server error"), event)
    return _build_response(500, "Server error")
  if definitions.Connections.USERNAME not in item:
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Not logged in"), event)
    return _build_response(401, "Not logged in")

  username = item[definitions.Connections.USERNAME]

  # Check for required components
  body = _fetch_body(event, logger)
  for attribute in [definitions.Messages.CONTENT, definitions.Messages.GROUP_ID]:
    if attribute not in body:
      error_message = "Improper message format: `{}' missing from message JSON".format(attribute)
      logger.debug(error_message)
      return _build_response(400, error_message)

  content = body[definitions.Messages.CONTENT]
  group = body[definitions.Messages.GROUP_ID]

  logger.debug("username: '{}', content: '{}', group: '{}'", username, content, group)

  # Validate that user is in group before sending message

  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  response = groups_table.query(
    ProjectionExpression="{}, {}".format(definitions.Groups.USERNAME, definitions.Groups.NICKNAME),
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Groups.GROUP_ID).eq(group)
  )
  logger.debug("response: {}", response)
  users = response.get("Items", [])
  # logger.debug("items: {}".format(items))
  # users = items # [item[definitions.Groups.USERNAME] for item in items if definitions.Groups.USERNAME in item]
  logger.debug("users: {}", users)

  ok = False
  nickname = None
  for user in users:
    if definitions.Groups.USERNAME in user:
      if user[definitions.Groups.USERNAME] == username:
        ok = True
        nickname = user[definitions.Groups.NICKNAME]
        break
    else:
      logger.error("Invalid record {}", user)
      _send_to_connection(connectionID, _build_response_detailed(500, action, "Internal server error"), event)
      return _build_response(500, "Internal Server Error")
  if not ok:
    logger.debug("User: {} not a member of {} users: {}", username, group, users)
    _send_to_connection(connectionID, _build_response_detailed(403, action, "user not a member of this group"), event)
    return _build_response(403, "user not member of group")

  messages_table = dynamodb.Table(definitions.Messages.TABLE_NAME)
  while True:
    timestamp = time.time_ns()
    logger.debug("Timestamp: {}", timestamp)
    try:
      messages_table.put_item(
        Item={
          definitions.Messages.GROUP_ID: group,
          definitions.Messages.TIMESTAMP: timestamp,
          definitions.Messages.USERNAME: username,
          definitions.Messages.CONTENT: content
          # definitions.Messages.GROUP_NAME: nickname,
          # definitions.Messages.INIT: False
        },
        ConditionExpression='attribute_not_exists({}) AND attribute_not_exists({})'.format(
          definitions.Messages.GROUP_ID,
          definitions.Messages.TIMESTAMP
        )
      )
      break
    except botocore.exceptions.ClientError as cle:
      # ConditionalCheckFailedException is okay (collision with timestamp), rest are not
      logger.debug("Exception raised")
      if cle.response['Error']['Code'] != 'ConditionalCheckFailedException':
        # TODO: Handle gracefully with a 500 response
        raise
      continue

  # Query all the users for their connectionIDs
  users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
  user_connIDs = {}
  for user in users:
    response = users_table.query(
      ProjectionExpression=definitions.Users.CONNECTION_ID,
      KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Users.USERNAME).eq(user[definitions.Users.USERNAME])
    )
    logger.debug("response: {}", response)
    items = response.get("Items", [])
    logger.debug("items: {}", items)
    if len(items) > 0:
      item = items[0]
    else:
      logger.error("user connection query returned not even an empty set items: {}", items)
      return _build_response(500, "Server error")
    if definitions.Users.CONNECTION_ID in item:
      conn_ID = item[definitions.Users.CONNECTION_ID]
      if conn_ID is not None:
        user_connIDs[user[definitions.Users.USERNAME]] = conn_ID
  logger.debug("user_connIDs: {}", user_connIDs)
  lambda_client = boto3.client("lambda")
  # Cycle through connectionID's sending out memo
  # TODO: send out to yourself first to lower latency for current user
  message = {
    definitions.Messages.USERNAME: username,
    definitions.Messages.GROUP_ID: group,
    definitions.Messages.TIMESTAMP: datetime.fromtimestamp(timestamp // 1000000000).strftime('%m/%d/%Y %H:%M'),
    definitions.Messages.CONTENT: content,
    definitions.Groups.NICKNAME: nickname
    # definitions.Messages.INIT: False
  }
  for user in user_connIDs:
    params = {
      "body": {
        "username": user,
        "all_messages": [[message]]
      }
    }
    invoke_response = lambda_client.invoke(
      FunctionName="chat-application-dev-fullActiveMessageRender",
      InvocationType="RequestResponse",
      Payload=json.dumps(params)
    )
    logger.debug("invoke_response: {}", invoke_response)
    payload = invoke_response['Payload'].read().decode()
    logger.debug("Payload: '{}' type: {}", payload, type(payload))
    payload_dict = json.loads(payload)
    active_message_html = payload_dict['body']
    logger.debug("Payload_dict: '{}' type: {}", payload_dict, type(payload_dict))
    params = {
      "body": {
        "all_messages": [message]
      }
    }
    invoke_response = lambda_client.invoke(
      FunctionName="chat-application-dev-sideMessageRender",
      InvocationType="RequestResponse",
      Payload=json.dumps(params)
    )
    logger.debug("invoke_response: {}", invoke_response)
    payload = invoke_response['Payload'].read().decode()
    logger.debug("Payload: '{}' type: {}", payload, type(payload))
    payload_dict = json.loads(payload)
    side_message_html = payload_dict['body']
    logger.debug("item: {} body: {}", item, side_message_html)
    data = {
      "action": action,
      "statusCode": 200,
      "body": {
        "group": group,
        "sideMessage": side_message_html,
        "activeMessage": active_message_html
      }
    }
    logger.debug("Data: {}", data)
    for user_individual_conn_ID in user_connIDs[user]:
      _send_to_connection(user_individual_conn_ID, data, event)

  return _build_response(200, "Message distributed to all connections")

