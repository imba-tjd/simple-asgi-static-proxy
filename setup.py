import setuptools

setuptools.setup(
    name='simple-asgi-static-proxy',
    version='0.32',
    install_requires=['urllib3>=2.0.0a1'],
    py_modules=['simple_asgi_static_proxy'],
    python_requires='>=3.10'  # union types as X | Y
)
