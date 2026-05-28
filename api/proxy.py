import json
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse, urljoin, quote
from http.server import BaseHTTPRequestHandler


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
# Fetch URL asli dengan User-Agent
# =============================================
def fetch_url(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        content = resp.read().decode("utf-8", errors="replace")
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return content, content_type


# =============================================
# Rewrite semua URL dalam konten m3u8
# Semua domain eksternal diganti jadi /live-proxy?url=...
# =============================================
def rewrite_m3u8(content, base_url, proxy_base):
    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # Rewrite URI= di dalam tag EXT-X
            def replace_uri(m):
                uri = m.group(1)
                full = resolve_url(uri, base_url)
                encoded = quote(full, safe="")
                return f'URI="{proxy_base}/live-proxy?url={encoded}"'
            line = re.sub(r'URI="([^"]+)"', replace_uri, line)
            result.append(line)
        elif stripped == "":
            result.append(line)
        elif stripped.startswith("http://") or stripped.startswith("https://"):
            encoded = quote(stripped, safe="")
            result.append(f"{proxy_base}/live-proxy?url={encoded}")
        elif stripped.endswith(".m3u8") or stripped.endswith(".ts") or stripped.endswith(".mp4") or stripped.endswith(".aac"):
            full = resolve_url(stripped, base_url)
            encoded = quote(full, safe="")
            result.append(f"{proxy_base}/live-proxy?url={encoded}")
        else:
            result.append(line)
    return "\n".join(result)


# =============================================
# Rewrite semua URL dalam konten MPD
# =============================================
def rewrite_mpd(content, base_url, proxy_base):
    def replace_url(m):
        url = m.group(1)
        if url.startswith("http://") or url.startswith("https://"):
            full = url
        else:
            full = resolve_url(url, base_url)
        encoded = quote(full, safe="")
        return f'"{proxy_base}/live-proxy?url={encoded}"'

    # Rewrite semua value attribute yang berupa URL atau path media
    content = re.sub(r'"(https?://[^"]+)"', replace_url, content)
    return content


# =============================================
# Resolve relative URL ke absolute
# =============================================
def resolve_url(path, base_url):
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return urljoin(base_url, path)


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
                content, _ = fetch_url(original_url)
            except Exception as e:
                self.send_response(502)
                self.end_headers()
                self.wfile.write(f"Fetch error: {e}".encode())
                return

            proxy_base = "https://proxy-live-session.vercel.app"

            if ch_type == "m3u8":
                content = rewrite_m3u8(content, original_url, proxy_base)
                content_type = "application/vnd.apple.mpegurl"
            elif ch_type == "mpd":
                content = rewrite_mpd(content, original_url, proxy_base)
                content_type = "application/dash+xml"
            else:
                content_type = "application/octet-stream"

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(content.encode("utf-8"))
            return

        # --- Route: /live-proxy?url=... ---
        if path.startswith("/live-proxy"):
            from urllib.parse import urlparse, parse_qs, unquote
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
                req = urllib.request.Request(target_url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    raw = resp.read()
                    ct = resp.headers.get("Content-Type", "application/octet-stream")

                # Kalau isinya m3u8 (chunklist), rewrite juga
                proxy_base = "https://proxy-live-session.vercel.app"
                if "mpegurl" in ct or target_url.endswith(".m3u8"):
                    text = raw.decode("utf-8", errors="replace")
                    text = rewrite_m3u8(text, target_url, proxy_base)
                    raw = text.encode("utf-8")
                    ct = "application/vnd.apple.mpegurl"
                elif "dash" in ct or target_url.endswith(".mpd"):
                    text = raw.decode("utf-8", errors="replace")
                    text = rewrite_mpd(text, target_url, proxy_base)
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
