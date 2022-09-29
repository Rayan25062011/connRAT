# -*- coding: utf-8 -*-

from __future__ import absolute_import
import six.moves.BaseHTTPServer
import datetime
import errno
import gzip
import os
import six.moves.socketserver
import sys
import tempfile

from cgi import parse_header, parse_multipart
from six.moves.urllib.parse import urlparse, ParseResult, parse_qs
from datetime import timedelta

import fire
import requests

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

WHSL = '\033[0m'
ENDL = '\033[0m'
REDL = '\033[0;31m'
GNSL = '\033[0;32m'
GREEN = '\033[1;32;40m'

def log(*args):
    message = "".join(args)
    message = f"{GNSL}[{REDL}CONNRAT{WHSL}{GNSL}]{WHSL} " + message
    sys.stdout.write(message + "\n")
    sys.stdout.flush()

CACHE_DIR = tempfile.gettempdir()
CACHE_DIR_NAMESPACE = "connRat"
CACHE_TIMEOUT = 60 * 60 * 24
CACHE_COMPRESS = False


def get_cache_dir(cache_dir):
    return os.path.join(cache_dir, CACHE_DIR_NAMESPACE)


def make_dirs(path):
    try:
        os.makedirs(path)
    except OSError as exc:
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def split_path(path):
    split_path = path.split('/')
    dirname = None
    filename = None
    if len(split_path) > 1:
        last_fragment = split_path[-1]
        if '.' not in last_fragment:
            filename = ''
            dirname = path
        else:
            filename = last_fragment
            dirname = '/'.join(split_path[:-1])
    else:
        filename = ''
        dirname = path
    return (dirname, filename)


def get_hashed_filepath(stub, method, parsed_url, params):
    hash_template = '{method}:{stub}{param_str}'
    param_str = ''
    if not stub:
        stub = 'index.html'
    if params:
        param_str = '&'.join(['{}={}'.format(k,v) for k,v in params.items()])
    elif method == 'GET' and parsed_url.query:
        param_str = parsed_url.query
    if param_str:
        param_str = '?'+param_str
    return hash_template.format(method=method, stub=stub, param_str=param_str)


class CacheHandler(six.moves.socketserver.ThreadingMixIn, six.moves.BaseHTTPServer.BaseHTTPRequestHandler):
    def get_cache(self, parsed_url, url, params={}):
        cachepath = '{}{}'.format(parsed_url.netloc, parsed_url.path)
        method = self.command
        dirpath, filepath_stub = split_path(cachepath)
        data = None
        filepath = get_hashed_filepath(stub=filepath_stub, method=method, parsed_url=parsed_url, params=params)

        cache_file = os.path.join(get_cache_dir(CACHE_DIR), dirpath, filepath)
        hit = False
        if os.path.exists(cache_file):
            if CACHE_TIMEOUT == 0:
                hit = True
            else:
                last_modified = datetime.datetime.utcfromtimestamp(os.path.getmtime(cache_file))
                valid_till = last_modified + timedelta(seconds=CACHE_TIMEOUT)
                now = datetime.datetime.utcnow()

                if valid_till > now:
                    hit = True

        fopen = gzip.open if CACHE_COMPRESS else open

        if hit:
            log(f"{GSNL}Cache hit{ENDL}")
            file_obj = fopen(cache_file, 'rb')
            data = file_obj.readlines()
            file_obj.close()
        else:
            log(f"{REDL}Cache miss{ENDL}")
            data = self.make_request(url=url, params=params, method=method)
            # make dirs before you write to file
            dirname, _filename = split_path(cache_file)
            make_dirs(dirname)
            file_obj = fopen(cache_file, 'wb+')
            file_obj.writelines(data)
            file_obj.close()
        return data

    def make_request(self, url, params={}, method='GET'):
        s = requests.Session()
        retries = Retry(total=3, backoff_factor=1)
        req = requests.Request(method, url, data=params)
        prepped = req.prepare()
        log(f"{REDL}Requesting{ENDL} " + url)
        s.mount('http://', HTTPAdapter(max_retries=retries))
        return s.send(prepped)

    def _normalize_params(self, params):
        for k, v in params.items():
            if isinstance(v, list):
                v_str = ','.join(v)
                params[k] = v_str
        return params

    def get_post_params(self):
        ctype, pdict = parse_header(self.headers['content-type'])
        postvars = {}
        if ctype == 'multipart/form-data':
            postvars = parse_multipart(self.rfile, pdict)
        elif ctype == 'application/x-www-form-urlencoded':
            length = int(self.headers['content-length'])
            postvars = parse_qs(self.rfile.read(length), keep_blank_values=1)
        return self._normalize_params(postvars)

    def normalize_parsed_url(self, parsed_url):
        path = parsed_url.path
        result = ParseResult(scheme=parsed_url.scheme,
                             netloc=parsed_url.netloc,
                             path=path.rstrip('/'),
                             params='',
                             query=parsed_url.query,
                             fragment=parsed_url.fragment)
        return result

    def process_request(self, params={}):
        url = self.path.lstrip('/')
        parsed_url = self.normalize_parsed_url(urlparse(url))
        log("URL to serve: ", url)
        data = self.get_cache(parsed_url, url, params)
        self.send_response(200)
        self.end_headers()
        self.wfile.writelines(data)

    def do_GET(self):
        self.process_request()

    def do_POST(self):
        params = self.get_post_params()
        self.process_request(params)


class CacheProxy(object):
    global host
    def activate(self, port=3030,
            cache_dir=CACHE_DIR,
            cache_timeout=CACHE_TIMEOUT,
            cache_compress=CACHE_COMPRESS):
        global CACHE_DIR
        global CACHE_TIMEOUT
        global CACHE_COMPRESS

        if cache_dir:
            CACHE_DIR = cache_dir

        CACHE_COMPRESS = cache_compress
        CACHE_TIMEOUT = cache_timeout

        if not os.path.isdir(CACHE_DIR):
            make_dirs(get_cache_dir(CACHE_DIR))
        
        server_address = ('', port)
        httpd = six.moves.BaseHTTPServer.HTTPServer(server_address, CacheHandler)

        print(f"""
        
                        \033[91m.---.  .--. .-----.{ENDL}
                        \033[91m: .; :: .; :`-. .-'{ENDL}
\033[93m .--.  .--. ,-.,-.,-.,-.\033[91m:   .':    :  : :{ENDL}  
\033[93m'  ..'' .; :: ,. :: ,. :\033[91m: :.`.: :: :  : :{ENDL}  
\033[93m`.__.'`.__.':_;:_;:_;:_;\033[91m:_;:_;:_;:_;  :_;{ENDL}  
                                           
                                           
                                           
        """)
        log(f"{GNSL}Server is started{ENDL} on port: {port}")


        _compressed = "(compressed) " if CACHE_COMPRESS else ""
        log("\033[93mFiles are cached succesfully\033[0m: {} at: {}".format(_compressed, get_cache_dir(CACHE_DIR)))

        _cache_timeout = CACHE_TIMEOUT if CACHE_TIMEOUT > 0 else '∞'
        log(f"\033[93mTimeout is set to\033[0m: {_cache_timeout} seconds")
        log(f"\033[93mCurrently serving\033[0m...")
        log(f"{REDL}Do not turn off your device n'or close this window!{ENDL}")

        httpd.serve_forever()

    def update(self, port=3030):
        server_address = ('', port)
        log("Updating...")
        try:
            os.system("git clone https://github.com/Rayan25062011")
            os.system("chmod +x connRAT.py")
            os.system("python3 connRAT.py")
            log(f"{REDL}[{ENDL}{GNSL}UPDATE{ENDL}{REDL}]{ENDL} Updated succesfully!")
        except:
            log(f"{REDL}[{ENDL}{GSNL}UPDATE{ENDL}{REDL}]{ENDL} Error while updating")
            sys.exit()


def make_cmd():
    fire.Fire(CacheProxy)

if __name__ == '__main__':
    make_cmd()