import urllib.request
req = urllib.request.Request('http://127.0.0.1:8001/api/health', method='OPTIONS', headers={
    'Host': '127.0.0.1:8001',
    'Connection': 'keep-alive',
    'Accept': '*/*',
    'Access-Control-Request-Method': 'GET',
    'Access-Control-Request-Headers': 'content-type',
    'Origin': 'http://127.0.0.1:5173',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-Dest': 'empty'
})
try:
    with urllib.request.urlopen(req) as response:
        print(response.status)
except urllib.error.HTTPError as e:
    print(f'Error: {e.code}')
    print(e.reason)
