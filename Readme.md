# Simple ASGI Static Proxy

* A proxy designed for **static** resources
* No security protection
* Support GET(Strong cache), HEAD(no cache), DELETE(remove cache)
* The client
  * Query string and request headers are ignored
* The server
  * Upstream must support HTTPS
* For browser: Use forward-proxy tools like `Header Editor`

## Usage

Install: `pip install git+https://github.com/imba-tjd/simple-asgi-static-proxy`

```py
from simple_asgi_static_proxy import SimpleASGIStaticProxy as App
app = App('mode1' --or-- {'mode2'}, opts)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app')
```

### Mode1

Works like a normal reverse proxy.

* Server: `app = App('example.com')`
* Client: `curl 127.0.0.1:8000/index.html`

### Mode2

The first part of path is parsed as domain.

* Server: `app = App({'example.com', 'example.org', 'whitelist_domain'})`. Or `set{}` to allow any domain
* Client: `curl 127.0.0.1:8000/example.com/index.html`

### Options

* Response HTTP Headers: By default it returns upstream headers combined with ex_resp_headers which you can override
* Disk cache: `cacher = shelve.open('cache')`
* Allow subdomain in mode2: `subdomain = True`
* Size limit: `maxsize = n (bytes)`. Defaults to 8MB. *0* indicates no limit. Upstream must response with Content-Length in order to use this

### TODO

* X-Forwarded-For：增加前一跳
* 限制总的访问频率
* 压缩未压缩内容
