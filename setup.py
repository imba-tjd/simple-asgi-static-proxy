import setuptools

setuptools.setup(
    name='simple-asgi-static-proxy',
    version='0.15',
    install_requires=['urllib3'],
    py_modules=['simple_asgi_static_proxy'],
    python_requires='>=3.9'
)
