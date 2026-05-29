import os
import re
import json
import requests
from flask import Flask, Response, request, abort

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


def rewrite_urls_m3u8(content, origin_base):
    """
    Rewrite semua URL absolut maupun relatif di dalam M3U8
    agar semua request balik lewat proxy ini.
    """
    lines = content.splitlines()
    result = []
    for line in lines:
        stripped = line.strip()
        # Lewati komentar/tag yang bukan URI
        if stripped.startswith("#") or stripped == "":
            result.append(line)
            continue
        # URL absolut
        if re.match(r"^https?://", stripped):
            encoded = requests.utils.quote(stripped, safe="")
            result.append(f"{PROXY_BASE}/fetch?url={encoded}")
        else:
            # URL relatif — gabung dengan origin_base
            full_url = origin_base.rstrip("/") + "/" + stripped.lstrip("/")
            encoded = requests.utils.quote(full_url, safe="")
            result.append(f"{PROXY_BASE}/fetch?url={encoded}")
    return "\n".join(result)


def rewrite_urls_mpd(content, origin_base):
    """
    Rewrite semua URL absolut di dalam MPD (DASH).
    Tangani BaseURL, SegmentTemplate, initialization, media.
    """
    def replace_abs(m):
        url = m.group(1)
        encoded = requests.utils.quote(url, safe="")
        return m.group(0).replace(url, f"{PROXY_BASE}/fetch?url={encoded}")

    # Rewrite semua https?://... di dalam atribut XML
    content = re.sub(
        r'(https?://[^\s"\'<>]+)',
        lambda m: f"{PROXY_BASE}/fetch?url={requests.utils.quote(m.group(1), safe='')}",
        content
    )
    return content


def fetch_and_rewrite(target_url):
    try:
        res = requests.get(target_url, headers=HEADERS, timeout=15)
    except requests.exceptions.RequestException as e:
        return Response(f"Fetch error: {e}", status=502)

    if not res.ok:
        return Response(f"Upstream error: {res.status_code}", status=502)

    content_type_raw = res.headers.get("Content-Type", "").lower()
    content = res.text

    # Tentukan tipe berdasarkan URL atau Content-Type
    url_lower = target_url.lower().split("?")[0]
    if url_lower.endswith(".m3u8") or "mpegurl" in content_type_raw or content.strip().startswith("#EXTM3U"):
        # Ambil base URL untuk resolve URL relatif
        origin_base = re.match(r"(https?://[^?#]+/)", target_url)
        origin_base = origin_base.group(1) if origin_base else target_url.rsplit("/", 1)[0] + "/"
        content = rewrite_urls_m3u8(content, origin_base)
        content_type = "application/vnd.apple.mpegurl"

    elif url_lower.endswith(".mpd") or "dash+xml" in content_type_raw:
        origin_base = target_url.rsplit("/", 1)[0] + "/"
        content = rewrite_urls_mpd(content, origin_base)
        content_type = "application/dash+xml"

    else:
        # File lain (chunklist, segment, dll) — stream langsung tanpa rewrite
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


# =============================================
# Route: /fetch?url=<encoded_url>
# Dipakai oleh worker.js maupun rekursif dari playlist
# =============================================
@app.route("/fetch")
def fetch_proxy():
    target_url = request.args.get("url", "").strip()
    if not target_url:
        abort(400, "Missing url parameter")
    if not re.match(r"^https?://", target_url):
        abort(400, "Invalid URL")
    return fetch_and_rewrite(target_url)


# =============================================
# Route: /live-session/<channel>
# Akses langsung berdasarkan nama channel
# =============================================
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


# =============================================
# Health check
# =============================================
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
