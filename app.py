import os
import re
import json
import requests
from flask import Flask, Response, request, abort
from urllib.parse import quote, urljoin

app = Flask(__name__)

PROXY_BASE = "https://hls-proxy-live-session.vidiraplay.biz.id"
CHANNELS_FILE = os.path.join(os.path.dirname(__file__), "channels.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


def load_channels():
    try:
        with open(CHANNELS_FILE, "r") as f:
            data = json.load(f)
        return {ch["name"]: ch for ch in data.get("channels", [])}
    except Exception:
        return {}


def rewrite_urls_m3u8(content, base_url):
    lines = content.splitlines()
    result = []
    uri_pattern = re.compile(r'(URI=")([^"]+)(")')

    for line in lines:
        stripped = line.strip()

        if stripped == "":
            result.append(line)
            continue

        if stripped.startswith("#"):
            # FIX: rewrite URI="..." di dalam tag seperti #EXT-X-KEY, #EXT-X-MAP
            def replace_uri(m):
                uri = m.group(2)
                full = urljoin(base_url, uri)
                return m.group(1) + f"{PROXY_BASE}/fetch?url={quote(full, safe='')}" + m.group(3)
            result.append(uri_pattern.sub(replace_uri, line))
            continue

        # Baris URL biasa (segment, sub-playlist)
        full = urljoin(base_url, stripped)
        result.append(f"{PROXY_BASE}/fetch?url={quote(full, safe='')}")

    return "\n".join(result)


def rewrite_urls_mpd(content, base_url):
    # Rewrite semua URL absolut
    content = re.sub(
        r'(https?://[^\s"\'<>]+)',
        lambda m: f"{PROXY_BASE}/fetch?url={quote(m.group(1), safe='')}",
        content
    )
    return content


def fetch_and_rewrite(target_url):
    try:
        res = requests.get(target_url, headers=HEADERS, timeout=15, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        return Response(f"Fetch error: {e}", status=502)

    if not res.ok:
        return Response(f"Upstream error: {res.status_code}", status=502)

    content_type_raw = res.headers.get("Content-Type", "").lower()
    content = res.text

    # Pakai URL final setelah redirect sebagai base
    final_url = res.url
    base_url = final_url.rsplit("/", 1)[0] + "/"

    url_lower = target_url.lower().split("?")[0]

    if url_lower.endswith(".m3u8") or "mpegurl" in content_type_raw or content.strip().startswith("#EXTM3U"):
        content = rewrite_urls_m3u8(content, base_url)
        content_type = "application/vnd.apple.mpegurl"

    elif url_lower.endswith(".mpd") or "dash+xml" in content_type_raw:
        content = rewrite_urls_mpd(content, base_url)
        content_type = "application/dash+xml"

    else:
        # Segment, key, dll — stream langsung
        return Response(
            res.content,
            status=res.status_code,
            headers={
                "Content-Type": res.headers.get("Content-Type", "application/octet-stream"),
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )

    return Response(
        content,
        status=200,
        headers={
            "Content-Type": content_type,
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        }
    )


@app.route("/fetch")
def fetch_proxy():
    target_url = request.args.get("url", "").strip()
    if not target_url:
        abort(400, "Missing url parameter")
    if not re.match(r"^https?://", target_url):
        abort(400, "Invalid URL")
    return fetch_and_rewrite(target_url)


@app.route("/live-session/<path:filename>")
def live_session(filename):
    channels = load_channels()

    matched = None
    for name, ch in channels.items():
        if name in filename.lower():
            matched = ch
            break

    if not matched:
        abort(404, "Channel not found")

    if not matched.get("proxy", False):
        abort(403, "Channel tidak dikonfigurasi untuk proxy")

    return fetch_and_rewrite(matched["url"])


@app.route("/")
def index():
    channels = load_channels()
    proxy_channels = [name for name, ch in channels.items() if ch.get("proxy")]
    return Response(
        f"Vidira HLS Proxy — {len(proxy_channels)} channel aktif",
        content_type="text/plain"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
