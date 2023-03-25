import urllib3
import logging
from typing import NamedTuple, Any, MutableMapping, Literal, Callable, Coroutine

SEND = Callable[[dict[str, Any]], Coroutine]  # ASGI send callable

__all__ = ['SimpleASGIStaticProxy']


class Response(NamedTuple):
    '''Used for caching'''
    status: int
    headers: list[tuple[str, str]]
    data: bytes


class SimpleASGIStaticProxy:
    ex_resp_headers = {  # 默认的额外响应头
        'Cache-Control': 'public, max-age=31536000, immutable',
        'Accept-Ranges': 'none'
    }

    def __init__(self, host: str | set[str], *, ex_resp_headers: dict[str, str] = {}, cacher: MutableMapping[str, Any] = {}, maxsize=2**23, subdomain=True, ua: str = 'DEFAULT'):
        if type(host) is str:
            self.check_host(host)
        else:  # Mode2
            for h in host:
                self.check_host(h)

        self.host = host
        self.cacher = cacher
        self.maxsize = maxsize
        self.allow_subdomain = subdomain
        self.client = urllib3.PoolManager(headers={'Accept-Encoding': 'gzip'}, timeout=3, retries=1)
        self.logger = logging.getLogger('uvicorn.error' if 'uvicorn' in __import__('sys').modules else __name__)
        if ex_resp_headers:
            self.ex_resp_headers = ex_resp_headers
        if ua != 'DEFAULT':
            self.ex_resp_headers['User-Agent'] = ua

        self.logger.info('proxy for %s', host)

    async def __call__(self, scope, receive, send: SEND):
        assert scope['type'] == 'http'
        if scope['method'] not in ('GET', 'HEAD', 'DELETE'):
            await self.refuse(send)
            return
        path: str = scope['path']

        url = self.cook_url(path)
        if url is None:
            await self.refuse(send)
            return

        await {'GET': self.serve_get,
               'HEAD': self.serve_head,
               'DELETE': self.serve_delete
               }[scope['method']](url, send)

    async def serve_head(self, url: str, send: SEND):
        upstream_resp = await self.do_request('HEAD', url)
        if isinstance(upstream_resp, int):
            await self.refuse(send, upstream_resp)
            return

        resp = Response(upstream_resp.status, list(upstream_resp.headers.items()), b'')

        await self.response(send, resp)

    async def serve_get(self, url: str, send: SEND):
        if resp := self.cacher.get(url):  # 已缓存
            await self.response(send, resp)
            return

        if self.maxsize:  # 需检查大小
            head_resp = await self.do_request('HEAD', url)
            if isinstance(head_resp, int):
                await self.refuse(send, head_resp)
                return

            cl = head_resp.headers.get('Content-Length')
            if cl is None or int(cl) > self.maxsize:
                await self.refuse(send)
                return

        upstream_resp = await self.do_request('GET', url)  # 作为客户端发请求
        if isinstance(upstream_resp, int):
            await self.refuse(send, upstream_resp)
            return

        headers_dic = dict(upstream_resp.headers) | self.ex_resp_headers
        resp = Response(upstream_resp.status, list(headers_dic.items()), upstream_resp.data)

        self.cacher.setdefault(url, resp)

        await self.response(send, resp)

    async def serve_delete(self, url: str, send: SEND):
        if url in self.cacher:
            del self.cacher[url]
            await self.refuse(send, 204)
        else:
            await self.refuse(send, 400)

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
                return  # 禁止访问根

            domain = path[1:path.find('/', 1)]  # 即使返回-1也没问题
            if not self.check_domain(domain):
                return  # 不在白名单

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
            return 400
        except urllib3.exceptions.MaxRetryError as e:
            self.logger.error(e)
            return 502  # Bad Gateway
        except urllib3.exceptions.TimeoutError as e:
            self.logger.error(e)
            return 504  # Gateway Timeout

    @staticmethod
    def check_host(h: str):
        '''阻止构造函数含有协议'''
        if h.startswith('http:') or h.startswith('https:') or '/' in h:
            raise ValueError(f'{h} is incorrect.')

    def check_domain(self, domain: str):
        '''请求的域名是否在白名单中，只会在Mode2下调用'''
        if not self.host or domain in self.host:
            return True  # host为空时直接放行

        if self.allow_subdomain:  # domain不在host里且启用subdomain，检查host里的不是domain的后缀
            for h in self.host:
                if domain.endswith(h):
                    return True

        return False
