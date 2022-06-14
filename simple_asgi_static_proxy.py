import urllib3
import logging
from typing import NamedTuple
import gzip


class Response(NamedTuple):
    '''Used for caching'''
    status: int
    headers: list[tuple[str, str]]
    data: bytes


class SimpleASGIStaticProxy:
    ex_resp_headers = [
        ('Cache-Control', 'public, max-age=31536000, immutable')
    ]

    def __init__(self, host: str | set[str], ex_resp_headers=None, cacher={}):
        '''host shouldn't contain protocol. cacher can be passed in dict-like obj.'''
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

        if not (resp := self.cacher.get(url)):
            if not self.check_size(url):
                await self.forbidden(send)
                return

            urllib3_resp = self.client.request('GET', url, preload_content=False)
            resp = self.make_response(urllib3_resp, self.ex_resp_headers)
            urllib3_resp.release_conn()
            self.cacher.setdefault(url, resp)

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

    async def response(self, send, resp: Response):
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

    @staticmethod
    def make_response(urllib3_resp: urllib3.HTTPResponse, ex_resp_headers: list[tuple[str, str]]):
        '''if upstream response is gzipped, response it. Otherwise gzip it by myself.'''
        headers = list(urllib3_resp.headers.items())
        data = urllib3_resp.read(decode_content=False)

        if urllib3_resp.headers.get('Content-Encoding') != 'gzip':
            data = gzip.compress(data)
            headers += [('Content-Encoding', 'gzip'), ('Content-Length', len(data))]

        headers += ex_resp_headers

        return Response(urllib3_resp.status, headers, data)

    def check_size(self, url: str):
        resp = self.client.request('HEAD', url)
        return int(resp.headers.get('Content-Length')) < 10 * 2**20
