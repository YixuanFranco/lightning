from django.conf import settings
from wechatpy.client import WeChatClient
from wechatpy.client.api import WeChatWxa
from wechatpy.session.redisstorage import RedisStorage
from api_basebone.utils.redis import redis_client

session = RedisStorage(redis_client)


def wrap(api, app_id):
    return api(
        client=WeChatClient(appid=app_id, secret=settings.WECHAT_APP_MAP[app_id]['appsecret'], session=session)
    )


def wxa(app_id):
    return wrap(WeChatWxa, app_id=app_id)
