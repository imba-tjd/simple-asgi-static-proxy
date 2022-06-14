# Simple ASGI Static Proxy

* A simple proxy for **static** resources
* No security protection

## Usage

### Server

Install: `pip install git+https://github.com/imba-tjd/simple-asgi-static-proxy`

```py
from simple_asgi_static_proxy import SimpleASGIStaticProxy as App
app = App('github.githubassets.com')
app2 = App({'github.githubassets.com', 'raw.githubusercontent.com'})

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app')
```

### Client

* Use forward-proxy tools such as `Header Editor`
* Must and only support gzip

## TODO

* 先HEAD请求，获得Content-Length，控制最大文件大小
