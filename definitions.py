class Users:
  TABLE_NAME     = "users"
  USERNAME       = "username"
  PASSWORD       = "password"
  CONNECTION_ID  = "connectionID"
  HASH_KEY       = USERNAME


class Connections:
  TABLE_NAME     = "connections"
  CONNECTION_ID  = "connectionID"
  USERNAME       = "username"
  HASH_KEY       = CONNECTION_ID


class Groups:
  TABLE_NAME      = "groups"
  GROUP_ID        = "groupID"
  USERNAME        = "username"
  JOIN_TIMESTAMP  = "joinTimestamp"
  ADMIN           = "admin"
  NICKNAME        = "nickname"
  EXCLUSION_LIST  = "exclusionList"
#  LEFT            = "leftGroup"
#  LEFT_TIMESTAMP  = "leftTimestamp"
  HASH_KEY        = GROUP_ID
  RANGE_KEY       = USERNAME


class Messages:
  TABLE_NAME  = "messages"
  GROUP_ID    = "groupID"
  TIMESTAMP   = "sendTimestamp"
  USERNAME    = "username"
  CONTENT     = "content"
#  INIT        = "init"
#  GROUP_NAME  = "nickname"
  HASH_KEY    = GROUP_ID
  RANGE_KEY   = TIMESTAMP
