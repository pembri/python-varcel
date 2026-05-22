from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import urllib.parse
import re

app = Flask(__name__)
CORS(app)

RAPIDAPI_KEY = "562ef3b0d6mshe01d3ade47117b1p1d6a93jsn1f4d947f6e65"
RAPIDAPI_HOST = "youtube-info-download-api.p.rapidapi.com"
BASE_API_URL = "https://python-varcel.vercel.app/api"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json"
}

def extract_video_id(url):
    patterns = [
        r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

@app.route('/api', methods=['GET', 'POST'])
def api_handler():
    action = request.args.get('action')

    # ==========================================
    # ALUR 1: PROXY DOWNLOAD
    # ==========================================
    if action == 'download':
        stream_url = request.args.get('url')
        title = request.args.get('title', 'audio')
        ext = request.args.get('ext', 'mp3')

        if not stream_url:
            return jsonify({"error": "Missing stream URL"}), 400

        stream_url = urllib.parse.unquote(stream_url)
        title = urllib.parse.unquote(title)

        def generate():
            try:
                r = requests.get(stream_url, stream=True, timeout=60)
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        yield chunk
            except:
                pass

        content_types = {'mp3':'audio/mpeg','wav':'audio/wav','m4a':'audio/mp4','webm':'audio/webm'}
        content_type = content_types.get(ext.lower(), 'application/octet-stream')
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).strip() or "audio"

        return Response(generate(), headers={
            'Content-Disposition': f'attachment; filename="{safe_title}.{ext}"',
            'Content-Type': content_type,
            'Cache-Control': 'no-cache'
        })

    # ==========================================
    # ALUR 2: POLL PROGRESS
    # ==========================================
    if action == 'progress':
        progress_url = request.args.get('url')
        if not progress_url:
            return jsonify({"error": "Missing progress URL"}), 400
        progress_url = urllib.parse.unquote(progress_url)
        try:
            r = requests.get(progress_url, headers=HEADERS, timeout=10)
            return jsonify(r.json())
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    # ==========================================
    # ALUR 3: GENERATE INFO
    # ==========================================
    url = None
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        url = data.get('url')
    else:
        url = request.args.get('url')

    if not url:
        return jsonify({"success": False, "error": "Silakan masukkan URL YouTube yang valid"}), 400

    try:
        video_id = extract_video_id(url)
        encoded = urllib.parse.quote(url)

        # Ambil thumbnail langsung dari YouTube (tidak perlu API)
        thumbnail = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""

        # Ambil title & duration dari YouTube oEmbed (gratis, tanpa API key)
        title = 'YTAudio Cloud'
        duration = 0
        try:
            oembed = requests.get(
                f"https://www.youtube.com/oembed?url={encoded}&format=json",
                timeout=10
            )
            oembed_data = oembed.json()
            title = oembed_data.get('title', 'YTAudio Cloud')
        except:
            pass

        # Request download mp3
        dl_resp = requests.get(
            f"https://{RAPIDAPI_HOST}/ajax/download.php?format=mp3&add_info=0&url={encoded}&audio_quality=128&allow_extended_duration=false&no_merge=false",
            headers=HEADERS,
            timeout=15
        )
        dl_data = dl_resp.json()

        if not dl_data.get('success'):
            return jsonify({"success": False, "error": "Gagal memulai proses download"}), 400

        progress_url = dl_data.get('progress_url', '')

        return jsonify({
            'success': True,
            'title': title,
            'thumbnail': thumbnail,
            'duration': duration,
            'progress_url': progress_url,
            'base_api_url': BASE_API_URL
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Gagal memproses video: {str(e)}"
        }), 500
