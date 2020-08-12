import json
import boto3
from jinja2 import BaseLoader

class S3Loader(BaseLoader):
  """
  Loads a Jinja template from AWS S3 Bucket
  """
  def __init__(self, bucketName, logger):
    self.bucket_name = bucketName
    self.s3_resource = boto3.resource('s3')
    self.logger = logger

  def get_source(self, environment, template):
    obj = self.s3_resource.Object(self.bucket_name, template)
    source = obj.get()["Body"].read().decode("utf-8")
    self.logger.debug("Template from source: '{}'", source)
    path = None
    uptodate = lambda: True
    return source, path, uptodate


def _build_response(status_code, body):
  """
  Builds a barebones response with status code and body message
  """
  if not isinstance(body, str):
    body = json.dumps(body)
  return {"statusCode": status_code, "body": body}

def _build_response_detailed (status_code: int, action: str, body: object):
  """
  Builds a more detailed response with status code, action type, and body message
  """
  if not isinstance(body, str):
    body = json.dumps(body)
  return {"statusCode": status_code, "action": action, "body": body}

def _fetch_body (event, logger):
  """
  Pull out and decode the body to an incoming JSON message
  """
  try:
    return json.loads(event.get("body", ""))
  except json.JSONDecodeError as jde:
    logger.debug("JSONDecodeError for 'body': {}", jde)
    return {}

def _send_to_connection(connection_id, data, event):
  gatewayapi = boto3.client(
    "apigatewaymanagementapi",
    endpoint_url="https://{domain}/{stage}".format(
      domain=event["requestContext"]["domainName"],
      stage=event["requestContext"]["stage"]
    )
  )
  return gatewayapi.post_to_connection(
    ConnectionId=connection_id,
    Data=json.dumps(data).encode('utf-8')
  )
