import urllib3
import logging
from typing import NamedTuple


class Urllib3Response(NamedTuple):
    status: int
    headers: list[tuple[str, str]]
    data: bytes


class SimpleASGIStaticProxy:
    ex_resp_headers = [
        ('Cache-Control', 'public, max-age=31536000, immutable')
    ]

    def __init__(self, host: str | set[str], ex_resp_headers=None, cacher={}):
        if type(host) is str:
            self.check_host(host)
        else:
            for h in host:
                self.check_host(h)

        self.host = host
        self.cacher = cacher
        self.client = urllib3.PoolManager(timeout=3, headers={'Accept-Encoding': 'gzip'})
        self.logger = logging.getLogger(__name__)
        if ex_resp_headers:
            self.ex_resp_headers = ex_resp_headers

    async def __call__(self, scope, receive, send):
        assert scope['type'] == 'http'
        assert scope['method'] in ('GET', 'HEAD')

        path: str = scope['path']
        self.logger.info(path)

        if type(self.host) is str:
            url = 'https://' + self.host + path
        else:
            domain = path[1:path.index('/', 1)]
            if self.host and domain not in self.host:
                await self.forbidden(send)
                return
            url = 'https://' + path[1:]

        if not (resp := self.cacher.get(path)):
            resp_raw = self.client.request('GET', url)
            resp = Urllib3Response(resp_raw.status, list(resp_raw.headers.items()) +
                                   self.ex_resp_headers, resp_raw.data)
            self.cacher.setdefault(path, resp)

        await self.response(send, resp)

    async def forbidden(self, send):
        await send({
            'type': 'http.response.start',
            'status': 403,
        })
        await send({
            'type': 'http.response.body',
            'body': b''
        })

    async def response(self, send, resp: Urllib3Response):
        await send({
            'type': 'http.response.start',
            'status': resp.status,
            'headers': resp.headers
        })
        await send({
            'type': 'http.response.body',
            'body': resp.data
        })

    @staticmethod
    def check_host(h: str):
        if h.startswith('http:') or h.startswith('https:') or '/' in h:
            raise ValueError(f'{h} is incorrect.')
