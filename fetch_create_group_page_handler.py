import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("fetch_create_group_page_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

s3 = boto3.resource('s3')

action = "fetchCreateGroupPage"

def fetch_create_group_page (event, context):
  """
  Endpoint to get the create group page
  """
  logger.info("Group creation page via WebSocket")
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

  obj = s3.Object('chat-application-upload-bucket-11097', 'create_group_page.html')
  body = obj.get()["Body"].read().decode("utf-8")
  _send_to_connection(connectionID, _build_response_detailed(200, action, body), event)
  return _build_response(200, "Create Group page fetched")