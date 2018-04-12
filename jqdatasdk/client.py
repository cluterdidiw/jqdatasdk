# coding=utf-8
from .utils import *
from .api import *
import thriftpy
from thriftpy.rpc import make_client
import msgpack
import time
from os import path
import platform
import sys
import pandas as pd


thrift_path = path.join(sys.modules["ROOT_DIR"], "jqdata.thrift")
thrift_path = path.abspath(thrift_path)
module_name = path.splitext(path.basename(thrift_path))[0]
thrift = None
with open(thrift_path) as f:
    thrift = thriftpy.load_fp(f, "jqdata_thrift")


class JQDataClient(object):

    _instance = None

    @classmethod
    def instance(cls):
        return cls._instance

    def __init__(self, host, port, username="", password="", retry_cnt=30):
        assert host, "host is required"
        assert port, "port is required"
        assert username, "username is required"
        assert password, "password is required"
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.inited = False
        self.retry_cnt = retry_cnt

    def ensure_auth(self):
        if not self.inited:
            if not self.username or self.username == "":
                raise RuntimeError("not inited")
            self.client = make_client(thrift.JqDataService, self.host, self.port)
            self.inited = True
            response = self.client.auth(self.username, self.password)
            if not response.status:
                self.__class__._instance = None
                raise self.get_error(response)
            else:
                self.__class__._instance = self
                #print("auth success")

    def _reset(self):
        if self.client:
            self.client.close()
            self.client = None
        self.inited = False

    def get_error(self, response):
        err = None
        if six.PY2:
            system = platform.system().lower()
            if system == "windows":
                err = Exception(response.error.encode("gbk"))
            else:
                err = Exception(response.error.encode("utf-8"))
        else:
            err = Exception(response.error)
        return err

    def __call__(self, method, **kwargs):
        request = thrift.St_Query_Req()
        request.method_name = method
        request.params = msgpack.packb(kwargs)
        import tempfile

        err, result = None, None
        for idx in range(self.retry_cnt):
            d = tempfile.gettempdir()
            import os, random, string
            name2 = ''.join(random.sample(string.ascii_letters + string.digits, 10))
            file = open(os.path.join(d, name2), "w+b")
            try:
                self.ensure_auth()
                response = self.client.query(request)
                if response.status:
                    buffer = response.msg
                    if six.PY2:
                        file.write(buffer)
                    else:
                        file.write(bytes(buffer, "ascii"))
                    file.seek(0)
                    result = pd.read_pickle(file.name)
                else:
                    err = self.get_error(response)
                break
            except KeyboardInterrupt as e:
                self._reset()
                err = e
                raise
            except OSError as e:
                self._reset()
                err = e
                time.sleep(idx * 2)
                continue
            except Exception as e:
                self._reset()
                err = e
                break
            finally:
                if os.path.exists(file.name):
                    file.close()
                    os.unlink(file.name)

        if result is None:
            if isinstance(err, Exception):
                raise err

        return result

    def __getattr__(self, method):
        return lambda **kwargs: self(method, **kwargs)


