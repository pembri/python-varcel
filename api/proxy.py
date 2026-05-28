import json
import re
import urllib.request
from urllib.parse import urlparse, urljoin, quote, parse_qs, unquote
from http.server import BaseHTTPRequestHandler

# URL yang terekspos ke client — selalu cdn-server
PROXY_BASE = "https://cdn-server.vidiraplay.biz.id"

# =============================================
# Load channels.json
# =============================================
def load_channels():
    try:
        with open("channels.json", "r") as f:
            data = json.load(f)
            return data.get("channels", [])
    except Exception:
        return []

# =============================================
# Cari channel berdasarkan filename
# =============================================
def find_channel(filename):
    channels = load_channels()
    for ch in channels:
        if ch["name"] in filename:
            return ch
    return None

# =============================================
# Fetch URL asli
# =============================================
def fetch_url(url):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36",
        "Referer": origin + "/",
        "Origin": origin,
        "Accept": "*/*",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Connection": "keep-alive",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read()
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return content, content_type

# =============================================
# Resolve relative URL ke absolute
# =============================================
def resolve_url(path, base_url):
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(base_url, path)

# =============================================
# Rewrite semua URL dalam konten m3u8
# Semua URL → cdn-server.vidiraplay.biz.id/live-proxy?url=...
# =============================================
def rewrite_m3u8(content, base_url):
    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Rewrite URI= di dalam tag EXT-X-KEY, EXT-X-MAP, dll
            def replace_uri(m):
                uri = m.group(1)
                full = resolve_url(uri, base_url)
                encoded = quote(full, safe="")
                return f'URI="{PROXY_BASE}/live-proxy?url={encoded}"'
            line = re.sub(r'URI="([^"]+)"', replace_uri, line)
            result.append(line)
        elif stripped == "":
            result.append(line)
        else:
            # Baris URL (absolute atau relative)
            full = resolve_url(stripped, base_url)
            encoded = quote(full, safe="")
            result.append(f"{PROXY_BASE}/live-proxy?url={encoded}")
    return "\n".join(result)

# =============================================
# Rewrite semua URL dalam konten MPD
# =============================================
def rewrite_mpd(content, base_url):
    def replace_url(m):
        url = m.group(1)
        full = resolve_url(url, base_url)
        encoded = quote(full, safe="")
        return f'"{PROXY_BASE}/live-proxy?url={encoded}"'
    content = re.sub(r'"(https?://[^"]+)"', replace_url, content)
    return content

# =============================================
# Main Handler
# =============================================
class handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path

        # --- Route: /live-session/<nama>.<ext> ---
        if path.startswith("/live-session/"):
            filename = path.replace("/live-session/", "").split("?")[0].lower()
            channel = find_channel(filename)

            if not channel:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Channel not found")
                return

            original_url = channel["url"]
            ch_type = channel["type"]

            try:
                raw, _ = fetch_url(original_url)
                content = raw.decode("utf-8", errors="replace")
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(f"Fetch error: {e}".encode())
                return

            if ch_type == "m3u8":
                content = rewrite_m3u8(content, original_url)
                content_type = "application/vnd.apple.mpegurl"
            elif ch_type == "mpd":
                content = rewrite_mpd(content, original_url)
                content_type = "application/dash+xml"
            else:
                content_type = "application/octet-stream"

            body = content.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
            return

        # --- Route: /live-proxy?url=... ---
        if path.startswith("/live-proxy"):
            parsed = urlparse(path)
            params = parse_qs(parsed.query)
            target_url = params.get("url", [None])[0]

            if not target_url:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Missing url param")
                return

            target_url = unquote(target_url)

            try:
                raw, ct = fetch_url(target_url)

                # Kalau responsnya m3u8 (chunklist), rewrite juga
                if "mpegurl" in ct or target_url.split("?")[0].endswith(".m3u8"):
                    text = raw.decode("utf-8", errors="replace")
                    text = rewrite_m3u8(text, target_url)
                    raw = text.encode("utf-8")
                    ct = "application/vnd.apple.mpegurl"
                elif "dash" in ct or target_url.split("?")[0].endswith(".mpd"):
                    text = raw.decode("utf-8", errors="replace")
                    text = rewrite_mpd(text, target_url)
                    raw = text.encode("utf-8")
                    ct = "application/dash+xml"

                self.send_response(200)
                self.send_header("Content-Type", ct)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.end_headers()
                self.wfile.write(raw)
                return

            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(f"Proxy error: {e}".encode())
                return

        # --- Halaman depan ---
        html = b"""<!DOCTYPE html>
<html>
<head><title>Vidira Proxy</title></head>
<body>
<h1>Vidira Proxy</h1>
<p>Gunakan: /live-session/nama-channel.m3u8 atau .mpd</p>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        pass
