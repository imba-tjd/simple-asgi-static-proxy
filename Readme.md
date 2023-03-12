# Simple ASGI Static Proxy

* A proxy designed for **static** resources
* No security protection
* The client
  * Can only use GET
  * Query string and request headers are ignored
* The server
  * Upstream must support HTTPS
  * Return whatever upstream returns
* For browser: Use forward-proxy tools like `Header Editor`

## Usage

Install: `pip install git+https://github.com/imba-tjd/simple-asgi-static-proxy`

```py
from simple_asgi_static_proxy import SimpleASGIStaticProxy as App
app = App('mode1' --or-- {'mode2'}, kw_opts)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app')
```

### Mode1

Works like a normal reverse proxy.

Server: `app = App('example.com')`.

Client: `curl 127.0.0.1:8000/index.html`.

### Mode2

The first part of path is considered domain.

Server: `app = App({'example.com', 'example.org', 'whitelist_domain'})`. Use `set{}` to allow any domain.

Client: `curl 127.0.0.1:8000/example.com/index.html`.

### Options

* Response HTTP Headers: By default it returns upstream headers combined with ex_resp_headers. You can override `ex_resp_headers`
* Disk cache: `cacher = dict-like-obj`
* Subdomain(mode2): `subdomain = True`
* Size limit: `maxsize = n bytes`. Defaults to 8MB. *0* indicates no limit. Upstream must response with Content-Length in order to use this
* UA: `ua = 'xxx' or ''`

## TODO

* 日志
