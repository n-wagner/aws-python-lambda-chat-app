import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("logout_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

s3 = boto3.resource('s3')

action = "logout"

def logout (event, context):
  """
  Handles a logout request via WebSocket
  """
  logger.info("Login request via WebSocket")
  logger.debug("event: {}".format(str(event)))
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("connectionID: {}".format(connectionID))

  # Query the connections Table and remove the current user
  connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
  local_var = ":user"
  result = connections_table.update_item(
    Key={
      definitions.Connections.CONNECTION_ID: connectionID
    },
    UpdateExpression="set {} = {}".format(
      definitions.Connections.USERNAME, 
      local_var
    ),
    ExpressionAttributeValues={
      local_var: None
    },
    ReturnValues="UPDATED_OLD"
  )
  logger.debug("Result: {}".format(result))
  # If there was a current user, remove the connection ID from the user Table
  if result['ResponseMetadata']['HTTPStatusCode'] == 200 and 'Attributes' in result:
    if definitions.Connections.USERNAME in result['Attributes']:
      logger.debug(result['Attributes'][definitions.Connections.USERNAME])
      if result['Attributes'][definitions.Connections.USERNAME] is not None:
        username = result['Attributes'][definitions.Connections.USERNAME]
        users_table = dynamodb.Table(definitions.Users.TABLE_NAME)
        local_var = ":connID"
        result = users_table.update_item(
          Key={
            definitions.Users.USERNAME: username
          },
          UpdateExpression="delete {} {}".format(
            definitions.Users.CONNECTION_ID,
            local_var
          ),
          ExpressionAttributeValues={
            local_var: set([connectionID])
          },
          ReturnValues="UPDATED_NEW"
        )
        logger.debug("Updated result: {}".format(result))
  else:
    logger.error("Connections table not properly updated - result: {}".format(result))
    _send_to_connection(connectionID, _build_response_detailed(500, action, "Internal server error"), event)
    return _build_response(500, "Internal server error")
  # TODO: Send the login page to the client
  obj = s3.Object('chat-application-upload-bucket-11097', 'login_page.html')
  body = obj.get()["Body"].read().decode("utf-8")
  _send_to_connection(connectionID, _build_response_detailed(200, action, body), event)
  return _build_response(200, "Disconnection success")