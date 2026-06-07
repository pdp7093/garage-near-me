#!/usr/bin/env python3
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8000'
paths = [
    '/',
    '/index',
    '/admin',
    '/admin/',
    '/admin/garages',
    '/admin/garage-detail/2',
    '/admin/garage-detail/dashboard',
    '/mechanic/dashboard',
    '/customer/index',
    '/garage-details?id=2',
    '/css/bootstrap.css',
    '/js/components.js',
    '/manifest.json',
]

print('Running smoke tests against', BASE)
for p in paths:
    url = BASE + p
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=5) as r:
            code = r.getcode()
            final = r.geturl()
            print(f'{p:30} -> {code}  final: {final}')
    except urllib.error.HTTPError as e:
        print(f'{p:30} -> HTTP {e.code}  final: {e.geturl()}')
    except Exception as e:
        print(f'{p:30} -> ERROR: {e}')
