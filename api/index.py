from http.server import BaseHTTPRequestHandler
import json

class handler(BaseHTTPRequestHandler):

    def do_GET(self):

        data = {
            "status": "online",
            "message": "Halo dari Python Vercel",
            "creator": "Pembri"
        }

        self.send_response(200)
        self.send_header(
            'Content-type',
            'application/json'
        )
        self.end_headers()

        self.wfile.write(
            json.dumps(data).encode()
        )

        return
