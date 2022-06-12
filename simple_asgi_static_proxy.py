import urllib3
import logging


class SimpleASGIStaticProxy:
    ex_headers = [
        ('Cache-Control', 'public, max-age=31536000, immutable')
    ]

    def __init__(self, host: str, ex_headers=None, cacher={}):
        self.host = 'https://' + host
        self.cacher = cacher
        self.client = urllib3.PoolManager(timeout=5)
        self.logger = logging.getLogger(f'{__name__}.{host}')
        if ex_headers:
            self.ex_headers = ex_headers

    async def __call__(self, scope, receive, send):
        assert scope['type'] == 'http'
        assert scope['method'] in ('GET', 'HEAD')

        path: str = scope['path']
        self.logger.info(path)

        if not (resp := self.cacher.get(path)):
            resp = self.client.request('GET', self.host+path)
            self.cacher.setdefault(path, resp)

        await send({
            'type': 'http.response.start',
            'status': resp.status,
            'headers': resp.headers.items() + self.ex_headers
        })
        await send({
            'type': 'http.response.body',
            'body': resp.data
        })
