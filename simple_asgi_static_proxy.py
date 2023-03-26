import urllib3
import logging
from typing import NamedTuple, Any, MutableMapping, Literal, Callable, Coroutine

SCOPE = dict[str, Any]
SEND = Callable[[dict[str, Any]], Coroutine]  # ASGI send callable

__all__ = ['SimpleASGIStaticProxy', 'Option']


class Response(NamedTuple):
    '''Used for caching'''
    status: int
    headers: list[tuple[str, str]]
    data: bytes


class Option(NamedTuple):
    ex_resp_headers: dict[str, str] = {
        'Cache-Control': 'public, max-age=31536000, immutable',
        'Accept-Ranges': 'none'
    }
    cacher: MutableMapping[str, Any] = {}
    maxsize: int = 2**23
    subdomain: bool = True
    method: list[str] = ['GET', 'HEAD']


class RefuseError(Exception):
    '''Used for return empty body with status code'''
    @property
    def status(self) -> int:
        if self.args:
            assert len(self.args) == 1 and isinstance(self.args[0], int)
            return self.args[0]
        else:
            return 404


class ResponseError(Exception):
    '''Used for return Response, not actually Error'''
    @property
    def response(self) -> Response:
        assert isinstance(self.args[0], Response)
        return self.args[0]


class SimpleASGIStaticProxy:
    def __init__(self, host: str | set[str], op: Option):
        if type(host) is str:
            self.check_host(host)
        else:  # Mode2
            for h in host:
                self.check_host(h)

        self.host = host
        self.op = op
        self.client = urllib3.PoolManager(headers={'Accept-Encoding': 'br, gzip'}, timeout=3, retries=1)
        self.logger = logging.getLogger('uvicorn.error' if 'uvicorn' in __import__('sys').modules else __name__)

        self.logger.info('proxy for %s', host or 'any')

    async def __call__(self, scope: SCOPE, receive, send: SEND):
        assert scope['type'] == 'http'
        try:
            await self.serve(scope)
        except RefuseError as e:
            await self.refuse(send, e.status)
        except ResponseError as e:
            await self.response(send, e.response)

    async def serve(self, scope):
        if scope['method'] not in self.op.method:
            raise RefuseError
        path: str = scope['path']

        url = self.cook_url(path)

        await {'GET': self.serve_get,
               'HEAD': self.serve_head,
               'DELETE': self.serve_delete
               }[scope['method']](url, scope)

    async def serve_head(self, url: str, scope):
        upstream_resp = await self.do_request('HEAD', url)
        raise ResponseError(Response(upstream_resp.status, list(upstream_resp.headers.items()), b''))

    async def serve_get(self, url: str, scope: SCOPE):
        if resp := self.op.cacher.get(url):  # 已缓存
            raise ResponseError(resp)

        req_headers: dict[bytes, bytes] = dict(scope['headers'])
        if b'If-Modified-Since' in req_headers or b'If-None-Match' in req_headers:
            raise RefuseError(304)  # Not Modified

        if self.op.maxsize:  # 需检查大小
            head_resp = await self.do_request('HEAD', url)

            cl = head_resp.headers.get('Content-Length')
            if cl is None or int(cl) > self.op.maxsize:
                raise RefuseError

        upstream_resp = await self.do_request('GET', url)  # 作为客户端发请求

        headers_dic = dict(upstream_resp.headers) | self.op.ex_resp_headers
        resp = Response(upstream_resp.status, list(headers_dic.items()), upstream_resp.data)

        self.op.cacher.setdefault(url, resp)  # 添加缓存

        raise ResponseError(resp)

    async def serve_delete(self, url: str, scope):
        if url in self.op.cacher:
            del self.op.cacher[url]
            raise RefuseError(204)
        else:
            raise RefuseError(400)

    @staticmethod
    async def refuse(send: SEND, status=403):
        await send({
            'type': 'http.response.start',
            'status': status,
        })
        await send({
            'type': 'http.response.body',
            'body': b''
        })

    @staticmethod
    async def response(send: SEND, resp: Response):
        await send({
            'type': 'http.response.start',
            'status': resp.status,
            'headers': resp.headers
        })
        await send({
            'type': 'http.response.body',
            'body': resp.data
        })

    def cook_url(self, path: str):
        '''根据客户端请求的路径生成向上游请求的URL'''
        if type(self.host) is str:
            return 'https://' + self.host + path
        else:  # Mode2
            path = path.removeprefix('https://').removeprefix('http://')
            if path[-1] == '/' or path.endswith('/favicon.ico'):
                raise RefuseError  # 禁止访问根

            domain = path[1:path.find('/', 1)]  # 即使返回-1也没问题
            if not self.check_domain(domain):
                raise RefuseError  # 不在白名单

            return 'https://' + path[1:]

    async def do_request(self, method: Literal['GET'] | Literal['HEAD'], url: str):
        '''作为客户端请求，处理了已知异常'''
        try:
            resp = self.client.request(method, url, preload_content=False)
            resp._body = resp.read(decode_content=False)  # type: ignore
            resp.release_conn()
            return resp
        except urllib3.exceptions.NameResolutionError as e:
            self.logger.error(e)
            raise RefuseError(400)
        except urllib3.exceptions.MaxRetryError as e:
            self.logger.error(e)
            raise RefuseError(502)  # Bad Gateway
        except urllib3.exceptions.TimeoutError as e:
            self.logger.error(e)
            raise RefuseError(504)  # Gateway Timeout

    @staticmethod
    def check_host(h: str):
        '''阻止构造函数含有协议'''
        if h.startswith('http:') or h.startswith('https:') or '/' in h:
            raise ValueError(f'{h} is incorrect.')

    def check_domain(self, domain: str):
        '''请求的域名是否在白名单中，只会在Mode2下调用'''
        if not self.host or domain in self.host:
            return True  # host为空时直接放行

        if self.op.subdomain:  # domain不在host里且启用subdomain，检查host里的不是domain的后缀
            for h in self.host:
                if domain.endswith(h):
                    return True
        return False
