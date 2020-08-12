import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("leave_group_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb", 
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "leaveGroup"

def leave_group (event, callback):
  """
  Leave a selected group
  """
  logger.info("Leaving a group")
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

  # Validate passed parameters

  body = _fetch_body(event, logger)
  for attribute in [definitions.Groups.GROUP_ID]:
    if attribute not in body:
      error_message = "Improper message format: `" + attribute + "' missing from message JSON"
      logger.debug(error_message)
      _send_to_connection(connectionID, _build_response_detailed(400, action, error_message), event)
      return _build_response(400, error_message)
  
  group = body[definitions.Groups.GROUP_ID]
  logger.debug("group_id: {}".format(group))

  # Validate user is a member of the group

  local_name = ":exclusion"
  #local_name_2 = ":leaveTimestmp"
  timestamp = time.time_ns()
  logger.debug("Leaving timestamp: {}".format(timestamp))
  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  try:
    response = groups_table.update_item(
      Key={
        definitions.Groups.GROUP_ID: group,
        definitions.Groups.USERNAME: username
      },
      # TODO: List append for the exclusion list
      UpdateExpression="set {} = list_append({}, {})".format(
        definitions.Groups.EXCLUSION_LIST,
        definitions.Groups.EXCLUSION_LIST,
        local_name
      ),
      ConditionExpression='attribute_exists({})'.format(
        definitions.Groups.GROUP_ID
      ),
      ExpressionAttributeValues={
        local_name: [timestamp]
      },
      ReturnValues="UPDATED_NEW"
      # ProjectionExpression="{}, {}".format(definitions.Groups.USERNAME, definitions.Groups.NICKNAME),
      # KeyConditionExpression=boto3.dynamodb.conditions.Key(definitions.Groups.GROUP_ID).eq(group)
    )
    logger.debug("response: {}".format(response))
  except botocore.exceptions.ClientError as e:
    # ConditionalCheckFailedException is okay, rest are not
    logger.debug("Exception raised")
    if e.response['Error']['Code'] != 'ConditionalCheckFailedException':
      logger.debug("Unexpected exception: {}".format(e))
      _send_to_connection(connectionID,_build_response_detailed(500, action, "Internal Server Error"), event)
      return _build_response(500, "Unexpected exception")
    else:
      logger.debug("User: {} not a member of {}".format(username, group))
      _send_to_connection(connectionID, _build_response_detailed(403, action, "user not a member of this group"), event)
      return _build_response(403, "user not member of group")

  _send_to_connection(connectionID, _build_response_detailed(200, action, "Successfully left group"), event)
  return _build_response(200, "Successfully left group")