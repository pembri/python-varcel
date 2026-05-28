from http.server import BaseHTTPRequestHandler
import urllib.request
import urllib.parse

ALLOWED_DOMAINS = [
    'op-group1-swiftservehd-1.dens.tv',
    'd25tgymtnqzu8s.cloudfront.net'
]

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        
        if 'url' not in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b'Missing url param')
            return
        
        target_url = params['url'][0]
        target_parsed = urllib.parse.urlparse(target_url)
        
        if target_parsed.netloc not in ALLOWED_DOMAINS:
            self.send_response(403)
            self.end_headers()
            self.wfile.write(b'Domain not allowed')
            return
        
        try:
            req = urllib.request.Request(
                target_url,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Mobile Safari/537.36',
                    'Referer': 'https://vidiraplay.biz.id/',
                    'Origin': 'https://vidiraplay.biz.id',
                    'Accept': '*/*',
                    'Accept-Language': 'id-ID,id;q=0.9',
                    'sec-fetch-site': 'cross-site',
                    'sec-fetch-mode': 'no-cors',
                    'sec-fetch-dest': 'video'
                }
            )
            with urllib.request.urlopen(req, timeout=10) as res:
                content = res.read()
                content_type = res.headers.get('Content-Type', 'application/octet-stream')
                
                self.send_response(200)
                self.send_header('Content-Type', content_type)
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(content)
                
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(f'HTTP Error {e.code}: {e.reason}'.encode())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode())
