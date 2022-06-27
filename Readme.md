# Simple ASGI Static Proxy

* A simple proxy for **static** resources
* No security protection

## Usage

### Server

* Install: `pip install git+https://github.com/imba-tjd/simple-asgi-static-proxy`
* Mode1: Pass a single domain str to the constructor. Path will append to the domain and send
* Mode2: Pass domains set as allow lists or `set()` to the constructor. The first part of the path will be treated as domain. Subdomain is not supported yet
* Disk cache: Pass a dict-like-obj to `cacher` parameter

```py
from simple_asgi_static_proxy import SimpleASGIStaticProxy as App
app = App('github.githubassets.com')
app2 = App({'github.githubassets.com', 'raw.githubusercontent.com'})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app')
```

### Client

* In Browser, use forward-proxy tools such as `Header Editor`
* Must and only support gzip
* Can only use GET
