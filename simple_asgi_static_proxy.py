import urllib3
import logging
from typing import NamedTuple, Any, MutableMapping, Literal


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

    async def __call__(self, scope, receive, send):
        assert scope['type'] == 'http'
        assert scope['method'] in ('GET', 'HEAD')
        path: str = scope['path']

        url = self.cook_url(path)
        if url is None:
            await self.refuse(send)
            return

        if resp := self.cacher.get(url):  # 已缓存
            await self.response(send, resp)
            return

        if not self.check_size(url):  # 过大
            await self.refuse(send)
            return

        urllib3_resp = await self.do_request(scope['method'], url, send)
        if urllib3_resp is None:
            return

        resp = self.cook_response(urllib3_resp)
        urllib3_resp.release_conn()

        self.cacher.setdefault(url, resp)

        await self.response(send, resp)

    async def refuse(self, send, status=403):
        await send({
            'type': 'http.response.start',
            'status': status,
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

    def cook_url(self, path: str):
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

    async def do_request(self, method: Literal['GET'] | Literal['HEAD'], url: str, send):
        '''作为客户端请求，处理了异常'''
        try:
            return self.do_get(url) if method == 'GET' else self.do_head(url)
        except urllib3.exceptions.MaxRetryError as e:
            self.logger.exception(e)
            await self.refuse(send, 502)  # Bad Gateway
        except urllib3.exceptions.TimeoutError as e:
            self.logger.exception(e)
            await self.refuse(send, 504)  # Gateway Timeout
        # TODO: 域名不对

    def do_get(self, url: str):
        return self.client.request('GET', url, preload_content=False)

    def do_head(self, url: str):
        return self.client.request('HEAD', url)

    def cook_response(self, urllib3_resp: urllib3.response.BaseHTTPResponse):
        data = urllib3_resp.read(decode_content=False)

        # if self.enable_gzip and not urllib3_resp.headers.get('Content-Encoding') and (ct := urllib3_resp.headers.get('Content-Type')) and (
        #         ct.startswith('text') or ct.startswith('application/json') or ct.startswith('image/svg+xml')):
        #     data = gzip.compress(data)
        #     urllib3_resp.headers['Content-Encoding'] = 'gzip'
        #     urllib3_resp.headers['Content-Length'] = str(len(data))

        # urllib3 HTTPHeaderDict doesn't support |
        headers = list((dict(urllib3_resp.headers) | self.ex_resp_headers).items())

        return Response(urllib3_resp.status, headers, data)

    @staticmethod
    def check_host(h: str):
        '''阻止构造函数含有协议'''
        if h.startswith('http:') or h.startswith('https:') or '/' in h:
            raise ValueError(f'{h} is incorrect.')

    def check_size(self, url: str):
        '''启用max_size时用HEAD获得目标文件大小，与max_size比较'''
        if not self.maxsize:
            return True
        resp = self.client.request('HEAD', url)
        cl = resp.headers.get('Content-Length')
        if cl is None:
            return False
        return int(cl) < self.maxsize

    def check_domain(self, domain: str):
        '''请求的域名是否在白名单中，只会在Mode2下调用'''
        if not self.host or domain in self.host:
            return True  # host为空时直接放行

        if self.allow_subdomain:  # domain不在host里且启用subdomain，检查host里的不是domain的后缀
            for h in self.host:
                if domain.endswith(h):
                    return True

        return False
