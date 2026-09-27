import urllib.request
req = urllib.request.Request('http://127.0.0.1:8001/api/health', method='OPTIONS', headers={
    'Origin': 'http://127.0.0.1:5173',
    'Access-Control-Request-Method': 'GET'
})
try:
    with urllib.request.urlopen(req) as response:
        print(response.status)
        print(response.headers['Access-Control-Allow-Origin'])
except Exception as e:
    print(e)
