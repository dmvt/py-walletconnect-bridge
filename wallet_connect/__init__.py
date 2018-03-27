import sys
import argparse

import asyncio
import aiohttp
import uvloop
from aiohttp import web
import boto3

import wallet_connect.keystore
from wallet_connect.push_notifications import PushNotificationsService
from wallet_connect.errors import KeystoreWriteError, KeystoreFetchError, FirebaseError, KeystoreTokenExpiredError, InvalidApiKey

routes = web.RouteTableDef()

API='io.wallet.connect.api_gateway'
REDIS='io.wallet.connect.redis'
PUSH='io.wallet.connect.push_notifications'
KEY='key'
LOCAL='local'
SERVICE='service'

def error_message(message):
  return {"message": message}


def get_redis_master(app):
  if app[REDIS][LOCAL]:
    return app[REDIS][SERVICE]
  sentinel = app[REDIS][SERVICE]
  return sentinel.master_for('mymaster')


@routes.get('/hello')
async def hello(request):
  return web.Response(text="hello world")


async def check_authorization(request):
  if 'Authorization' not in request.headers:
    raise InvalidApiKey
  api_key = request.headers['Authorization']
  if request.app[API][KEY] != api_key:
    raise InvalidApiKey


@routes.post('/create-shared-connection')
async def create_shared_connection(request):
  try:
    await check_authorization(request)
    request_json = await request.json()
    token = request_json['token']
    redis_conn = get_redis_master(request.app)
    await keystore.add_shared_connection(redis_conn, token)
    return web.Response(status=201)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except KeystoreWriteError as kwe:
    return web.json_response(error_message("Error writing to db"), status=500)
  except InvalidApiKey as iak:
      return web.json_response(error_message("Unauthorized"), status=401)
  except:
    return web.json_response(error_message("Error unknown"), status=500)


@routes.post('/update-connection-details')
async def update_connection_details(request):
  request_json = await request.json()
  try:
    token = request_json['token']
    encrypted_payload = request_json['encryptedPayload']
    redis_conn = get_redis_master(request.app)
    await keystore.update_connection_details(redis_conn, token, encrypted_payload)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except KeystoreTokenExpiredError as ktee:
    return web.json_response(error_message("Connection sharing token has expired"), status=500)
  except:
    return web.json_response(error_message("Error unknown"), status=500)
  return web.Response(status=202)


@routes.post('/get-connection-details')
async def get_connection_details(request):
  try:
    await check_authorization(request)
    request_json = await request.json()
    token = request_json['token']
    redis_conn = get_redis_master(request.app)
    connection_details = await keystore.get_connection_details(redis_conn, token)
    if connection_details:
      json_response = {"encryptedPayload": connection_details}
      return web.json_response(json_response)
    else: 
      return web.Response(status=204)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except InvalidApiKey as iak:
      return web.json_response(error_message("Unauthorized"), status=401)
  except:
    return web.json_response(error_message("Error unknown"), status=500)


@routes.post('/initiate-transaction')
async def initiate_transaction(request):
  try:
    await check_authorization(request)
    request_json = await request.json()
    transaction_uuid = request_json['transactionUuid']
    device_uuid = request_json['deviceUuid']
    encrypted_payload = request_json['encryptedPayload']
    notification_title = request_json['notificationTitle']
    notification_body = request_json['notificationBody']
    redis_conn = get_redis_master(request.app)
    await keystore.add_transaction(redis_conn, transaction_uuid, device_uuid, encrypted_payload)
    data_message = {"transactionUuid": transaction_uuid }
    push_notifications_service = request.app[PUSH][SERVICE]
    await push_notifications_service.notify_single_device(
        registration_id=device_uuid,
        message_title=notification_title,
        message_body=notification_body,
        data_message=data_message)
    return web.Response(status=201)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except FirebaseError as fe:
    return web.json_response(error_message("Error pushing notifications through Firebase"), status=500)
  except InvalidApiKey as iak:
      return web.json_response(error_message("Unauthorized"), status=401)
  except:
      return web.json_response(error_message("Error unknown"), status=500)


@routes.post('/get-transaction-details')
async def get_transaction_details(request):
  request_json = await request.json()
  try:
    transaction_uuid = request_json['transactionUuid']
    device_uuid = request_json['deviceUuid']
    redis_conn = get_redis_master(request.app)
    details = await keystore.get_transaction_details(redis_conn, transaction_uuid, device_uuid)
    json_response = {"encryptedPayload": details}
    return web.json_response(json_response)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except KeystoreFetchError as kfe:
    return web.json_response(error_message("Error retrieving transaction details"), status=500)
  except:
    return web.json_response(error_message("Error unknown"), status=500)


@routes.post('/add-transaction-hash')
async def add_transaction_hash(request):
  try:
    request_json = await request.json()
    transaction_uuid = request_json['transactionUuid']
    device_uuid = request_json['deviceUuid']
    transaction_hash = request_json['transactionHash']
    redis_conn = get_redis_master(request.app)
    await keystore.add_transaction_hash(redis_conn, transaction_uuid, device_uuid, transaction_hash)
    return web.Response(status=201)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except FirebaseError as fe:
    return web.json_response(error_message("Error pushing notifications through Firebase"), status=500)
  except InvalidApiKey as iak:
      return web.json_response(error_message("Unauthorized"), status=401)
  except:
      return web.json_response(error_message("Error unknown"), status=500)


@routes.post('/get-transaction-hash')
async def get_transaction_hash(request):
  try:
    await check_authorization(request)
    request_json = await request.json()
    transaction_uuid = request_json['transactionUuid']
    device_uuid = request_json['deviceUuid']
    redis_conn = get_redis_master(request.app)
    transaction_hash = await keystore.get_transaction_hash(redis_conn, transaction_uuid, device_uuid)
    if transaction_hash:
      json_response = {"transactionHash": transaction_hash}
      return web.json_response(json_response)
    else: 
      return web.Response(status=204)
  except KeyError as ke:
    return web.json_response(error_message("Incorrect input parameters"), status=400)
  except TypeError as te:
    return web.json_response(error_message("Incorrect JSON content type"), status=400)
  except InvalidApiKey as iak:
      return web.json_response(error_message("Unauthorized"), status=401)
  except:
    return web.json_response(error_message("Error unknown"), status=500)


def get_kms_parameter(param_name):
  ssm = boto3.client('ssm', region_name='us-east-2')
  response = ssm.get_parameters(Names=[param_name], WithDecryption=True)
  return response['Parameters'][0]['Value']


async def initialize_push_notifications(app):
  local = app[PUSH][LOCAL]
  if local:
    app[PUSH][SERVICE] = PushNotificationsService(debug=local)
  else:
    api_key = get_kms_parameter('fcm-server-key')
    session = aiohttp.ClientSession(loop=app.loop)
    app[PUSH][SERVICE] = PushNotificationsService(session=session, api_key=api_key)


async def initialize_keystore(app):
  if app[REDIS][LOCAL]:
    app[REDIS][SERVICE] = await keystore.create_connection(event_loop=app.loop)
  else:
    sentinels = get_kms_parameter('wallet-connect-redis-sentinels')
    app[REDIS][SERVICE] = await keystore.create_sentinel_connection(event_loop=app.loop,
                                                           sentinels=sentinels.split(','))


async def initialize_api_gateway(app):
  if app[API][LOCAL]:
    app[API][KEY] = 'dummy_api_key'
  else:
    app[API][KEY] = get_kms_parameter('wallet-connect-manager-api-key')


async def close_keystore(app):
  app[REDIS][SERVICE].close()
  await app[REDIS][SERVICE].wait_closed()


async def close_push_notification_connection(app):
  if app[PUSH][SERVICE].session:
    await app[PUSH][SERVICE].session.close()


def main(): 
  parser = argparse.ArgumentParser()
  parser.add_argument('--redis-local', action='store_true')
  parser.add_argument('--push-local', action='store_true')
  parser.add_argument('--api-local', action='store_true')
  args = parser.parse_args()

  app = web.Application()
  app[API] = {LOCAL: args.api_local}
  app[REDIS] = {LOCAL: args.redis_local}
  app[PUSH] = {LOCAL: args.push_local}
  app.on_startup.append(initialize_push_notifications)
  app.on_startup.append(initialize_keystore)
  app.on_startup.append(initialize_api_gateway)
  app.on_cleanup.append(close_keystore)
  app.on_cleanup.append(close_push_notification_connection)
  app.router.add_routes(routes)
  asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
  web.run_app(app)


if __name__ == '__main__':
  main()