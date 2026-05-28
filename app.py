from flask import Flask, Response, request
import requests
from urllib.parse import quote, unquote

app = Flask(__name__)

BASE_URL = 'https://op-group1-swiftservehd-1.dens.tv/h/h12/'
SOURCE_M3U8 = BASE_URL + '01.m3u8'
MY_URL = 'https://proxy-live-session-production.up.railway.app'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36',
    'Referer': 'https://op-group1-swiftservehd-1.dens.tv/',
    'Origin': 'https://op-group1-swiftservehd-1.dens.tv',
    'Accept': '*/*',
}

@app.route('/')
def index():
    return '<h2>M3U8 Proxy Server Running ✅</h2><p><a href="/live.m3u8">/live.m3u8</a></p>'

@app.route('/live.m3u8')
def proxy_m3u8():
    try:
        r = requests.get(SOURCE_M3U8, headers=HEADERS, timeout=10)
        lines = []
        for line in r.text.splitlines():
            s = line.strip()
            if s == '' or s.startswith('#'):
                lines.append(line)
            else:
                # Jadiin absolute URL dulu
                if not s.startswith('http'):
                    s = BASE_URL + s
                lines.append(f'{MY_URL}/seg?u={quote(s, safe="")}')
        return Response('\n'.join(lines),
            content_type='application/vnd.apple.mpegurl',
            headers={'Access-Control-Allow-Origin': '*', 'Cache-Control': 'no-cache'}
        )
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)

@app.route('/seg')
def proxy_seg():
    url = unquote(request.args.get('u', ''))
    if not url:
        return Response('Missing u', status=400)
    try:
        r = requests.get(url, headers=HEADERS, stream=True, timeout=15)
        return Response(
            r.iter_content(chunk_size=4096),
            content_type=r.headers.get('Content-Type', 'video/MP2T'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
