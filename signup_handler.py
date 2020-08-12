import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _fetch_body

logger = logging.getLogger("signup_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)


def signup (event, context):
  """
  Handles a register attempt via WebSocket
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
      return _build_response(400, error_message)
  username = body[definitions.Users.USERNAME]
  password = body[definitions.Users.PASSWORD]
  logger.debug("username: '{}', password: '{}'".format(username, password))
  # Queries for the password to the username from the Table
  users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
  response = users_table.query(
    ProjectionExpression=definitions.Users.USERNAME,
    KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Users.USERNAME).eq(username)
  )
  logger.debug("response: {}".format(response))
  items = response.get("Items", [])
  logger.debug("items: {}".format(items))
  # Check if username already exists
  if (len(items) >= 0):
    item = items[0]
    if len(item) != 0:
      return _build_response(401, "Invalid username")
  else:
    logger.error("username query returned not even an empty set items: {}".format(items))
    return _build_response(500, "Server error")
  # Creates the new user
  users_table.put_item(
    Item={
      definitions.Users.USERNAME: username,
      definitions.Users.PASSWORD: password,
      definitions.Users.CONNECTION_ID: [connectionID]
    }
  )
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
    return _build_response(500, "Internal server error")
  # TODO: Send blank home screen to client
  return _build_response(200, "Signup successful")