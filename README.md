# AWS Python Serverless Chat Application
A cloud based serverless chat application.

Currently entirely defined as a singular service.
Future revisions will be to break the application into
relevant services to take advantage of the microservices
architecture. The benefit is an application that does not
need to be fully redeployed with minor changes to
functionality or the development of new features.

## Features
 - User registration and login managed by the application
 - Chat group creation and adding users
 - Selection of groups for further detail
   - Messages grouped by timestamp
 - Loading older messages (greator than immediate 20)
 - Messaging to own groups (send/receive)
 - Leaving a group
 - Logging out of the application
 - Frontend rendering handled by AWS lambda via Jinja2
   HTML template rendering and DOM replacement

## Future Plans
 - Login/security managed by alternative means (perhaps
   AWS Cognito)
 - Breakdown of application to microservices/separate
   stacks
   - Involved restructuring of the project code
 - Documentation of how to recreate the project step-by-step
 - Frontend rendering delegated to React (current
   approach with Jinja is messy and not easily scalable)
   - Still have a service for syncing/declaring the
     appropriate S3 bucket
 - Leaving a group + rejoining indefinitely (gaps in
   between create "exclusion zones" where messages should
   not be loaded from backend)
 - Cleaner exception handling for frontend and backend
   (mess of botocore exceptions calling `raise' instead
   of gracefully returning and issues with invalid users
   entered on group creation screen not properly showing)
   - Adding also a user search field in group creation

## Relevant GitHub Issues
 - Cross stack reference resolution for local testing
   (attempting `Fn::ImportValue` assigns to env vars
   does not resolve locally - unsure about deployment-wise)
   https://github.com/serverless/serverless/pull/7147