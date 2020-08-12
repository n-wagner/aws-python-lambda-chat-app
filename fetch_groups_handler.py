import os
import json
import time
import logging
from datetime import datetime
import boto3
import botocore
import definitions
from chat_utilities import _build_response, _build_response_detailed, _fetch_body, _send_to_connection

logger = logging.getLogger("fetch_groups_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb",
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)

action = "fetchGroups"

def fetch_groups (event, context):
  """
  Fetch groups for side bar endpoint
  """
  logger.info("fetch groups request via WebSocket")
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

  groups_table = dynamodb.Table(definitions.Groups.TABLE_NAME)
  response = groups_table.scan(
    ProjectionExpression="{}, {}".format(definitions.Groups.GROUP_ID, definitions.Groups.NICKNAME),
    FilterExpression=boto3.dynamodb.conditions.Attr(definitions.Groups.USERNAME).eq(username)
  )
  items = response.get("Items", [])
  logger.debug("items: {}".format(str(items)))
  # How many groups there are
  item_len = len(items)
  logger.debug("groups: {}".format(item_len))
  last_messages = []
  # Query Last Message for each
  for group in items:
    local_name = ":grp"
    messages_table = dynamodb.Table(definitions.Messages.TABLE_NAME)

    # TODO: Need to do selective query here depending on if user has left the group or not

    response = messages_table.query(
      KeyConditionExpression="{} = {}".format(definitions.Messages.HASH_KEY, local_name),
      ExpressionAttributeValues={local_name: group[definitions.Groups.GROUP_ID]},
      Limit=1,
      ScanIndexForward=False
    )
    items = response.get("Items", [])
    logger.debug("items: {}".format(str(items)))
    message = items[0]
    logger.debug("message: {}".format(str(message)))
    last_messages.append(
      {
        definitions.Messages.USERNAME: message[definitions.Messages.USERNAME] if definitions.Messages.USERNAME in message else None,
        definitions.Messages.GROUP_ID: group[definitions.Groups.GROUP_ID],
        definitions.Messages.TIMESTAMP: datetime.fromtimestamp(message[definitions.Messages.TIMESTAMP] // 1000000000).strftime('%m/%d/%Y %H:%M'),
        definitions.Messages.CONTENT: message[definitions.Messages.CONTENT],
        definitions.Groups.NICKNAME: group[definitions.Groups.NICKNAME],
        # definitions.Messages.INIT: message[definitions.Messages.INIT] if definitions.Messages.INIT in message else False
      }
    )
  logger.debug("last_messages before sort: {}".format(last_messages))
  last_messages.sort(key=lambda item: item[definitions.Messages.TIMESTAMP], reverse=True)
  logger.debug("last_messages after sort: {}".format(last_messages))
  # Render messages
  params = {
    "body": {
      "all_messages": last_messages
    }
  }
  lambda_client = boto3.client("lambda")
  invoke_response = lambda_client.invoke(
    FunctionName="chat-application-dev-fetchChatRender",
    InvocationType="RequestResponse",
    Payload=json.dumps(params)
  )
  payload = invoke_response['Payload'].read().decode()
  logger.debug("Payload: '{}' type: {}".format(payload, type(payload)))
  payload_dict = json.loads(payload)
  logger.debug("Payload_dict: '{}' type: {}".format(payload_dict, type(payload_dict)))
  _send_to_connection(connectionID, _build_response_detailed(200, action, payload_dict["body"]), event)
  return _build_response(200, "Groups fetched")