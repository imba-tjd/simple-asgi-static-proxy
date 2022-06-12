# Simple ASGI Static Proxy

* A simple proxy for **static** resources
* No security protection

## Usage

### Server

Install: `pip install git+https://github.com/imba-tjd/simple-asgi-static-proxy`

```py
from simple_asgi_static_proxy import SimpleASGIStaticProxy as App
app = App('github.githubassets.com')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app')
```

### Client

* Use forward-proxy tools such as `Header Editor`.
