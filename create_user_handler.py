import os
import time
import logging
import boto3
import botocore
import definitions
import secrets
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("create_user_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb", 
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "createUser"

def create_user (event, context):
  """
  Endpoint to create a chat user 
  """
  logger.info("User creation via WebSocket")
  logger.debug("event: {}".format(str(event)))
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}".format(connectionID))

  # Check for required components
  body = _fetch_body(event, logger)
  for attribute in [definitions.Users.USERNAME, definitions.Users.PASSWORD]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      _send_to_connection(connectionID, _build_response_detailed(400, action, error_message), event)
      return _build_response(400, error_message)
  
  username = body[definitions.Users.USERNAME]
  if username == "System":
    _send_to_connection(connectionID, _build_response_detailed(401, action, "Forbidden Username"), event)
    return _build_response(401, "Forbidden Username")
  password = body[definitions.Users.PASSWORD]
  logger.debug("username: '{}', password: '{}'".format(username, password))
  users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
  try:
    users_table.put_item(
      Item={
        definitions.Users.USERNAME: username,
        definitions.Users.PASSWORD: password,
        definitions.Users.CONNECTION_ID: set([connectionID])
      },
      ConditionExpression='attribute_not_exists({})'.format(
        definitions.Users.USERNAME
      )
    )
  except botocore.exceptions.ClientError as e:
    # ConditionalCheckFailedException is okay, rest are not
    logger.debug(e)
    logger.debug("Exception raised")
    if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
      raise
    else:
      _send_to_connection(connectionID, _build_response_detailed(401, action, "Invalid username/password"), event)
      return _build_response(401, "Username not unique")
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
  # TODO: Send blank home screen to client
  _send_to_connection(connectionID, _build_response_detailed(200, action, "Login Success"), event)
  return _build_response(200, "User {} created".format(username))



