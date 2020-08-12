import os
import logging
import boto3
import definitions
from chat_utilities import _build_response

logger = logging.getLogger("connection_handler")
logger.setLevel(logging.DEBUG)

dynamodb = boto3.resource(
  "dynamodb", 
  endpoint_url="http://localhost:8000" if os.environ.get('IS_OFFLINE') == "true" else None
)


def connection_manager (event, context):
  """
  Handles CONNECT and DISCONNECT for WebSocket
  """
  connectionID = event["requestContext"].get("connectionId")
  logger.debug("event: {}".format(str(event)))
  logger.debug("connectionID: {}".format(connectionID))

  if event["requestContext"]["eventType"] == "CONNECT":
    logger.info("Incoming connect request")

    # Add the connection to the database
    connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
    connections_table.put_item(
      Item={
        definitions.Connections.CONNECTION_ID: connectionID
      }
    )
    return _build_response(200, "Connection success")

  elif event["requestContext"]["eventType"] == "DISCONNECT":
    logger.info("Incoming disconnect request")

    # Remove the connection from the database
    connections_table = dynamodb.Table(definitions.Connections.TABLE_NAME)
    result = connections_table.delete_item(
      Key={
        definitions.Connections.HASH_KEY: connectionID
      },
      ReturnValues="ALL_OLD"
    )
    logger.debug(result)
    # Removes connectionID from userTable on abrupt disconnect (no logout)
    if result['ResponseMetadata']['HTTPStatusCode'] == 200 and 'Attributes' in result:
      if definitions.Connections.USERNAME in result['Attributes']:
        if result['Attributes'][definitions.Connections.USERNAME] != None:
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
      return _build_response(500, "Internal server error")
    return _build_response(200, "Disconnection success")

  else:
    logger.error("Unexpected eventType for connection manager")
    return _build_response(500, "Unexpected eventType")