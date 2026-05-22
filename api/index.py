from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import urllib.parse
import re
import time

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

def get_info(video_url):
    encoded = urllib.parse.quote(video_url)
    r = requests.get(
        f"https://{RAPIDAPI_HOST}/ajax/info.php?url={encoded}",
        headers=HEADERS,
        timeout=15
    )
    return r.json()

def get_download(video_url, fmt='mp3'):
    encoded = urllib.parse.quote(video_url)
    r = requests.get(
        f"https://{RAPIDAPI_HOST}/ajax/download.php?format={fmt}&add_info=0&url={encoded}&audio_quality=128&allow_extended_duration=false&no_merge=false&audio_language=en",
        headers=HEADERS,
        timeout=15
    )
    return r.json()

def poll_progress(progress_url, max_wait=30):
    for _ in range(max_wait):
        r = requests.get(progress_url, headers=HEADERS, timeout=10)
        data = r.json()
        # Kalau sudah ada download_url, return
        dl_url = data.get('download_url') or data.get('url') or data.get('result')
        if dl_url:
            return dl_url
        # Kalau masih proses, tunggu 1 detik
        status = data.get('status') or data.get('progress')
        if status in ('failed', 'error'):
            return None
        time.sleep(1)
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

        dl_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Referer': 'https://www.youtube.com/',
        }

        def generate():
            try:
                r = requests.get(stream_url, stream=True, headers=dl_headers, timeout=60)
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        yield chunk
            except:
                pass

        content_types = {
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'm4a': 'audio/mp4',
            'webm': 'audio/webm'
        }
        content_type = content_types.get(ext.lower(), 'application/octet-stream')
        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).strip() or "audio"

        return Response(generate(), headers={
            'Content-Disposition': f'attachment; filename="{safe_title}.{ext}"',
            'Content-Type': content_type,
            'Cache-Control': 'no-cache'
        })

    # ==========================================
    # ALUR 2: GENERATE INFO
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
        # Step 1: Ambil info video
        info = get_info(url)
        title = info.get('title', 'YTAudio Cloud')
        thumbnail = info.get('thumbnail', '')
        duration = info.get('duration', 0)

        # Step 2: Request download mp3
        dl_data = get_download(url, fmt='mp3')
        if not dl_data.get('success'):
            return jsonify({"success": False, "error": "Gagal memproses video"}), 400

        progress_url = dl_data.get('progress_url')
        if not progress_url:
            return jsonify({"success": False, "error": "Tidak ada progress URL"}), 400

        # Step 3: Poll sampai dapat download URL
        final_url = poll_progress(progress_url)
        if not final_url:
            return jsonify({"success": False, "error": "Timeout menunggu proses download"}), 400

        # Buat format download lewat proxy
        supported_exts = [
            {'ext': 'mp3', 'label': 'MP3 (Audio Populer)'},
            {'ext': 'm4a', 'label': 'M4A (Original AAC)'},
            {'ext': 'wav', 'label': 'WAV (Kualitas Tinggi)'},
        ]

        formats_data = []
        for item in supported_exts:
            ext = item['ext']
            encoded_title = urllib.parse.quote(title)
            encoded_url = urllib.parse.quote(final_url)
            download_link = f"{BASE_API_URL}?action=download&ext={ext}&title={encoded_title}&url={encoded_url}"
            formats_data.append({
                'ext': ext,
                'label': item['label'],
                'url': download_link
            })

        return jsonify({
            'success': True,
            'title': title,
            'thumbnail': thumbnail,
            'duration': duration,
            'formats': formats_data
        })

    except Exception as e:
        return jsonify({
            'success': False,
            'error': f"Gagal memproses video: {str(e)}"
        }), 500
