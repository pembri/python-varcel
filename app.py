from flask import Flask, Response, request
import requests
import re
from urllib.parse import urljoin, urlparse, quote, unquote

app = Flask(__name__)

SOURCE_M3U8 = 'https://op-group1-swiftservehd-1.dens.tv/h/h12/index.m3u8'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://op-group1-swiftservehd-1.dens.tv/',
    'Origin': 'https://op-group1-swiftservehd-1.dens.tv',
}

def make_absolute(url, base):
    if url.startswith('http'):
        return url
    return urljoin(base, url)

@app.route('/')
def index():
    return '<h2>M3U8 Proxy Server Running ✅</h2><p><a href="/live.m3u8">/live.m3u8</a></p>'

@app.route('/live.m3u8')
def proxy_m3u8():
    try:
        r = requests.get(SOURCE_M3U8, headers=HEADERS, timeout=10)
        base = SOURCE_M3U8.rsplit('/', 1)[0] + '/'
        
        lines = []
        for line in r.text.splitlines():
            stripped = line.strip()
            if stripped == '' or stripped.startswith('#'):
                lines.append(line)
            else:
                abs_url = make_absolute(stripped, base)
                encoded = quote(abs_url, safe='')
                lines.append(f'https://proxy-live-session-production.up.railway.app/seg?u={encoded}')
        
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
        return Response('Missing u param', status=400)
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
