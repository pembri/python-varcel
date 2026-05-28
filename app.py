from flask import Flask, Response, request
import requests
import re
from urllib.parse import urljoin, urlparse, quote

app = Flask(__name__)

SOURCE_M3U8 = 'https://op-group1-swiftservehd-1.dens.tv/h/h12/index.m3u8'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://op-group1-swiftservehd-1.dens.tv/',
    'Origin': 'https://op-group1-swiftservehd-1.dens.tv',
}

def get_base_url(url):
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{'/'.join(parsed.path.split('/')[:-1])}/"

@app.route('/')
def index():
    return '<h2>M3U8 Proxy Server Running ✅</h2><p>Akses stream di <a href="/live.m3u8">/live.m3u8</a></p>'

@app.route('/live.m3u8')
def proxy_m3u8():
    try:
        r = requests.get(SOURCE_M3U8, headers=HEADERS, timeout=10)
        content = r.text
        base_url = get_base_url(SOURCE_M3U8)

        # Rewrite relative URL jadi absolute, lalu proxy
        lines = []
        for line in content.splitlines():
            if line.startswith('#'):
                lines.append(line)
            elif line.strip() == '':
                lines.append(line)
            else:
                # Kalau URL relative, jadiin absolute dulu
                if not line.startswith('http'):
                    line = urljoin(base_url, line)
                # Proxy lewat server kita
                lines.append(f'/segment?url={quote(line, safe="")}')

        result = '\n'.join(lines)
        return Response(result,
            content_type='application/vnd.apple.mpegurl',
            headers={
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache',
            }
        )
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)

@app.route('/segment')
def proxy_segment():
    seg_url = request.args.get('url')
    if not seg_url:
        return Response('Missing url param', status=400)
    try:
        r = requests.get(seg_url, headers=HEADERS, stream=True, timeout=15)
        return Response(
            r.iter_content(chunk_size=4096),
            content_type=r.headers.get('Content-Type', 'video/MP2T'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    except Exception as e:
        return Response(f'Error: {str(e)}', status=500)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
