import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("login_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "login"

def login (event, context):
  """
  Handles a login attempt via WebSocket
  """
  logger.info("Login request via WebSocket")
  logger.debug("event: {}".format(str(event)))
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}".format(connectionID))

  # Validates username and password fields are present and fetches them
  body = _fetch_body(event, logger)
  for attribute in [definitions.Users.USERNAME, definitions.Users.PASSWORD]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      _send_to_connection(connectionID, _build_response_detailed(400, action, error_message), event)
      return _build_response(400, error_message)
  username = body[definitions.Users.USERNAME]
  password = body[definitions.Users.PASSWORD]
  logger.debug("username: '{}', password: '{}'".format(username, password))
  # Queries for the password to the username from the Table
  users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
  response = users_table.query(
    ProjectionExpression=definitions.Users.PASSWORD,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Users.USERNAME).eq(username)
  )
  logger.debug("response: {}".format(response))
  items = response.get("Items", [])
  logger.debug("items: {}".format(items))
  if len(items) > 0:
    item = items[0]
  else:
    # Case: User does not exist
    logger.debug("No user with name: {}".format(username))
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Invalid username/password"), event)
    return _build_response(401, "Invalid username/password")
  # Validates username/password
  if definitions.Users.PASSWORD in item:
    correct_password = item[definitions.Users.PASSWORD]
    if (password != correct_password):
      _send_to_connection(connectionID, _build_response_detailed(401, action, "Invalid username/password"), event)
      return _build_response(401, "Invalid username/password")
  else:
    # Case: User record without a password field
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Invalid user record"), event)
    return _build_response(401, "Invalid user record")
  # Updates the user to have this connectionID appended
  local_var = ":connID"
  result = users_table.update_item(
    Key={
      definitions.Users.USERNAME: username
    },
    UpdateExpression="add {} {}".format(
      definitions.Users.CONNECTION_ID,
      local_var
    ),
    ExpressionAttributeValues={
      local_var: set([connectionID])
    },
    ReturnValues="UPDATED_NEW"
  )
  if result['ResponseMetadata']['HTTPStatusCode'] == 200 and 'Attributes' in result:
    logger.debug(result['Attributes'][definitions.Users.CONNECTION_ID])
  else:
    logger.error("User table not properly updated - result: {}".format(result))
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Internal server error"), event)
    return _build_response(500, "Internal server error")
  # Updates the connections Table to have the username added
  local_var = ":user"
  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  result = connections_table.update_item(
    Key={
      definitions.Connections.CONNECTION_ID: connectionID
    },
    UpdateExpression="set {} = {}".format(
      definitions.Connections.USERNAME, 
      local_var
    ),
    ExpressionAttributeValues={
      local_var: username
    },
    ReturnValues="UPDATED_NEW"
  )
  if result['ResponseMetadata']['HTTPStatusCode'] == 200 and 'Attributes' in result:
    logger.debug(result['Attributes'][definitions.Connections.USERNAME])
  else:
    logger.error("Connections table not properly updated - result: {}".format(result))
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Internal server error"), event)
    return _build_response(500, "Internal server error")
  # obj = s3.Object('chat-application-upload-bucket-11097', 'chat_template')
  _send_to_connection(connectionID, _build_response_detailed(200, action, "Login Success"), event)
  return _build_response(200, "Login successful")