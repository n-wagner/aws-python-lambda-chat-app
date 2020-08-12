import os
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
import secrets
import json
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("create_group_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb", 
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "createGroup"

def create_group (event, context):
  """
  Endpoint to create a chat group 
  """
  logger.info("Group creation via WebSocket")
  logger.debug("event: {}".format(str(event)))
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}".format(connectionID))

  # Validate that user is logged in

  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  response = connections_table.query(
    ProjectionExpression=definitions.Connections.USERNAME,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Connections.CONNECTION_ID).eq(connectionID)
  )
  logger.debug("response: {}".format(response))
  items = response.get("Items", [])
  logger.debug("items: {}".format(items))
  if (len(items) > 0):
    item = items[0]
  else:
    logger.error("user password query returned not even an empty set items: {}".format(items))
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Server error"), event)
    return _build_response(500, "Server error")
  if definitions.Connections.USERNAME not in item:
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Not logged in"), event)
    return _build_response(401, "Not logged in")

  username = item[definitions.Connections.USERNAME]

  # Check for required components
  body = _fetch_body(event, logger)
  for attribute in [definitions.Groups.NICKNAME, "users"]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      return _build_response(400, error_message)
  
  nickname = body[definitions.Groups.NICKNAME]
  users = json.loads(body["users"])
  logger.debug("nickname: '{}', username: '{}', users: '{}', users_type: {}".format(nickname, username, users, type(users)))
    
  # Validate that all users exist
  users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
  invalid_users = []
  online_users = []
  for user in users:
    if user == username:
      invalid_users.append(user)
      continue
    response = users_table.query(
      ProjectionExpression="{}, {}".format(
        definitions.Users.USERNAME, 
        definitions.Users.CONNECTION_ID
      ),
      KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Users.USERNAME).eq(user)
    )
    logger.debug("response: {}".format(response))
    items = response.get("Items", [])
    logger.debug("items: {}".format(items))
    if (len(items) > 0):
      item = items[0]
    else:
      invalid_users.append(user)
    # get all the connection IDs for online users
    if definitions.Users.CONNECTION_ID in item:
      online_users.extend(item[definitions.Users.CONNECTION_ID])
    if definitions.Users.USERNAME not in item:
      invalid_users.append(user)

  logger.debug("Invalid users: {}".format(invalid_users))

  if len(invalid_users) > 0:
    _send_to_connection(connectionID, _build_response_detailed(400, action, invalid_users), event)
    return _build_response(400, "Invalid users {}".format(invalid_users))

  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  group_id = secrets.token_urlsafe(16)
  timestamp = time.time_ns()
  logger.debug("Generated group_id: {} Timestamp: {}".format(group_id, timestamp))
  logger.debug("Users before if: {}".format(users))
  if (len(users) > 0):
    while True:
      try:
        groups_table.put_item(
          Item={
            definitions.Groups.GROUP_ID: group_id,
            definitions.Groups.USERNAME: username,
            definitions.Groups.JOIN_TIMESTAMP: timestamp,
            definitions.Groups.NICKNAME: nickname,
            # TODO Check if this does anything or if we need it
            definitions.Groups.EXCLUSION_LIST: list()
          },
          ConditionExpression='attribute_not_exists({}) AND attribute_not_exists({})'.format(
            definitions.Groups.GROUP_ID,
            definitions.Groups.USERNAME
          )
        )
        break
      except botocore.exceptions.ClientError as e:
        # ConditionalCheckFailedException is okay, rest are not
        logger.debug("Exception raised")
        if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
          logger.debug("Unexpected exception: {}".format(e))
          _send_to_connection(connectionID, _build_response_detailed(500, action, "Server Error"), event)
          return _build_response(500, "Unexpected exception: {}".format(e))
        else:
          group_id = secrets.token_urlsafe(16)
          logger.debug("Regenerated group_id: {}".format(group_id))
          continue
    logger.debug("Users before iteration: {}".format(users))
    for user in users:
      try:
        groups_table.put_item(
          Item={
            definitions.Groups.GROUP_ID: group_id,
            definitions.Groups.USERNAME: user,
            definitions.Groups.JOIN_TIMESTAMP: timestamp,
            definitions.Groups.NICKNAME: nickname,
            # TODO: Check if this does anything / if we need it
            definitions.Groups.EXCLUSION_LIST: list()
          },
          ConditionExpression='attribute_not_exists({}) AND attribute_not_exists({})'.format(
            definitions.Groups.GROUP_ID,
            definitions.Groups.USERNAME
          )
        )
      except botocore.exceptions.ClientError as e:
        # ConditionalCheckFailedException is okay, rest are not
        logger.debug(e)
        logger.debug("Exception raised - there should not be an issue adding users")
        _send_to_connection(connectionID, _build_response_detailed(500, action, "Server Error"), event)
        return _build_response(500, "Error adding additional users")
        # if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
        #   raise
        # else:
        #   group_id = secrets.token_urlsafe(16)
        #   continue
  # alert everyone a group has been made? send the init memo to all groups
    logger.debug("group created")
    message = "Group created"
  else:
    logger.debug("Self group attempted")
    message = "Cannot make a self group"

  # Init memo

  messages_table = dynamodb.Table(definitions.Messages.TABLE_NAME)
  try:
    message = {
      definitions.Messages.USERNAME: None,
      definitions.Messages.GROUP_ID: group_id,
      definitions.Messages.TIMESTAMP: timestamp,
      definitions.Messages.CONTENT: "Group created at: {}".format(datetime.fromtimestamp(timestamp // 1000000000).strftime('%m/%d/%Y %H:%M')),
      definitions.Groups.NICKNAME: nickname
      # definitions.Messages.INIT: True
    }
    messages_table.put_item(
      Item=message,
      ConditionExpression='attribute_not_exists({}) AND attribute_not_exists({})'.format(
        definitions.Messages.GROUP_ID,
        definitions.Messages.TIMESTAMP
      )
    )
  except botocore.exceptions.ClientError as e:
    # Should be no errors as this is the first message to be inserted
    logger.debug("Exception raised - error inserting init message")
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Server Error"), event)
    return _build_response(500, "Error inserting init message")
    
  # Send init message to all clients

  lambda_client = boto3.client("lambda")
  message[definitions.Messages.TIMESTAMP] = datetime.fromtimestamp(message[definitions.Messages.TIMESTAMP] // 1000000000).strftime('%m/%d/%Y %H:%M')
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
  logger.debug("invoke_response: {}".format(invoke_response))
  payload = invoke_response['Payload'].read().decode()
  logger.debug("Payload: '{}' type: {}".format(payload, type(payload)))
  payload_dict = json.loads(payload)
  side_message_html = payload_dict['body']
  logger.debug("online_users: {}".format(online_users))
  for online_user in online_users:
    _send_to_connection(online_user, _build_response_detailed(200, "init", side_message_html), event)

  # Success message to group creater

  _send_to_connection(connectionID, _build_response_detailed(200, action, "Group Created"), event)
  return _build_response(200, message)



