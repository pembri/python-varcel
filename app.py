import os
import re
import json
import requests
from flask import Flask, Response, request, abort
from urllib.parse import quote, urlparse, urljoin

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


def to_proxy_url(url):
    """Encode URL menjadi Railway /fetch?url=... """
    return f"{PROXY_BASE}/fetch?url={quote(url, safe='')}"


def resolve_url(href, base_url):
    """
    Resolve URL relatif maupun absolut terhadap base_url.
    Gunakan urljoin yang sudah handle ../ dan path relatif.
    """
    if re.match(r"^https?://", href):
        return href
    return urljoin(base_url, href)


def rewrite_urls_m3u8(content, base_url):
    """
    Rewrite SEMUA URL di dalam M3U8 agar semua request balik lewat proxy.
    Handle:
      - Baris URI biasa (chunklist, segment .ts, .aac, dll)
      - Tag #EXT-X-KEY:URI="..."
      - Tag #EXT-X-MAP:URI="..."
      - Tag #EXT-X-MEDIA:URI="..."
      - URL absolut maupun relatif
    """
    lines = content.splitlines()
    result = []

    # Pattern untuk tag yang mengandung URI="..."
    uri_tag_pattern = re.compile(r'(URI=")([^"]+)(")')

    for line in lines:
        stripped = line.strip()

        if stripped == "":
            result.append(line)
            continue

        if stripped.startswith("#"):
            # Cek apakah tag ini mengandung URI="..."
            def replace_uri(m):
                uri = m.group(2)
                full = resolve_url(uri, base_url)
                return m.group(1) + to_proxy_url(full) + m.group(3)

            new_line = uri_tag_pattern.sub(replace_uri, line)
            result.append(new_line)
            continue

        # Baris biasa = URL (absolut atau relatif)
        full = resolve_url(stripped, base_url)
        result.append(to_proxy_url(full))

    return "\n".join(result)


def rewrite_urls_mpd(content, base_url):
    """
    Rewrite SEMUA URL di dalam MPD (DASH).
    Handle:
      - URL absolut https?://...
      - <BaseURL>...</BaseURL>
      - initialization="..." dan media="..." di SegmentTemplate (relatif)
      - Atribut src="..." atau href="..."
    """

    # 1. Rewrite <BaseURL>URL</BaseURL>
    def replace_baseurl(m):
        url = m.group(1).strip()
        if re.match(r"^https?://", url):
            return f"<BaseURL>{to_proxy_url(url)}</BaseURL>"
        else:
            full = resolve_url(url, base_url)
            return f"<BaseURL>{to_proxy_url(full)}</BaseURL>"

    content = re.sub(r'<BaseURL>(.*?)</BaseURL>', replace_baseurl, content, flags=re.DOTALL)

    # 2. Rewrite URL absolut dalam atribut XML (initialization, media, src, href, dll)
    def replace_attr_abs(m):
        url = m.group(2)
        if re.match(r"^https?://", url):
            return m.group(1) + to_proxy_url(url) + m.group(3)
        return m.group(0)

    content = re.sub(r'((?:initialization|media|src|href)=")([^"]+)(")', replace_attr_abs, content)

    # 3. Rewrite sisa URL absolut yang masih tersisa di dalam atribut/teks
    def replace_abs(m):
        url = m.group(0)
        # Jangan double-encode yang sudah jadi proxy URL
        if url.startswith(PROXY_BASE):
            return url
        return to_proxy_url(url)

    content = re.sub(r'https?://[^\s"\'<>\]]+', replace_abs, content)

    return content


def fetch_and_rewrite(target_url):
    try:
        res = requests.get(target_url, headers=HEADERS, timeout=15, allow_redirects=True)
    except requests.exceptions.RequestException as e:
        return Response(f"Fetch error: {e}", status=502)

    if not res.ok:
        return Response(f"Upstream error: {res.status_code}", status=502)

    content_type_raw = res.headers.get("Content-Type", "").lower()

    # Gunakan URL final setelah redirect sebagai base
    final_url = res.url
    base_url = final_url.rsplit("/", 1)[0] + "/"

    # Cek tipe konten
    url_lower = target_url.lower().split("?")[0]
    is_m3u8 = (
        url_lower.endswith(".m3u8")
        or "mpegurl" in content_type_raw
        or res.text.strip().startswith("#EXTM3U")
    )
    is_mpd = url_lower.endswith(".mpd") or "dash+xml" in content_type_raw

    if is_m3u8:
        content = rewrite_urls_m3u8(res.text, base_url)
        content_type = "application/vnd.apple.mpegurl"
        return Response(
            content,
            status=200,
            headers={
                "Content-Type": content_type,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )

    elif is_mpd:
        content = rewrite_urls_mpd(res.text, base_url)
        content_type = "application/dash+xml"
        return Response(
            content,
            status=200,
            headers={
                "Content-Type": content_type,
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )

    else:
        # File lain (segment .ts, .mp4, .aac, key, dll) — stream langsung
        return Response(
            res.content,
            status=res.status_code,
            headers={
                "Content-Type": res.headers.get("Content-Type", "application/octet-stream"),
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            }
        )


# =============================================
# Route: /fetch?url=<encoded_url>
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
