from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from pytubefix import YouTube
from pytubefix.cli import on_progress
import requests
import urllib.parse
import re

app = Flask(__name__)
CORS(app)

def format_duration(seconds):
    if not seconds:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

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

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Referer': 'https://www.youtube.com/',
            'Origin': 'https://www.youtube.com',
        }

        def generate():
            try:
                r = requests.get(stream_url, stream=True, headers=headers, timeout=60)
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        yield chunk
            except Exception:
                pass

        content_types = {
            'mp3': 'audio/mpeg',
            'wav': 'audio/wav',
            'm4a': 'audio/mp4',
            'webm': 'audio/webm'
        }
        content_type = content_types.get(ext.lower(), 'application/octet-stream')

        safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c in ' -_']).strip()
        if not safe_title:
            safe_title = "audio"
        filename = f"{safe_title}.{ext}"

        response_headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': content_type,
            'Cache-Control': 'no-cache'
        }

        return Response(generate(), headers=response_headers)

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
        yt = YouTube(url, use_oauth=False, allow_oauth_cache=False)

        title = yt.title or 'YTAudio Cloud'
        thumbnail = yt.thumbnail_url or ''
        duration = yt.length or 0

        # Ambil stream audio terbaik
        audio_stream = yt.streams.filter(only_audio=True).order_by('abr').last()

        if not audio_stream:
            return jsonify({"success": False, "error": "Tidak ada stream audio tersedia untuk video ini"}), 400

        best_audio_url = audio_stream.url
        ext_original = audio_stream.subtype  # biasanya 'mp4' atau 'webm'

        base_api_url = "https://python-varcel.vercel.app/api"

        supported_exts = [
            {'ext': 'mp3', 'label': 'MP3 (Audio Populer)'},
            {'ext': 'wav', 'label': 'WAV (Kualitas Tinggi)'},
            {'ext': 'm4a', 'label': 'M4A (Original AAC)'}
        ]

        formats_data = []
        for item in supported_exts:
            ext = item['ext']
            label = item['label']
            encoded_title = urllib.parse.quote(title)
            encoded_url = urllib.parse.quote(best_audio_url)
            download_link = f"{base_api_url}?action=download&ext={ext}&title={encoded_title}&url={encoded_url}"
            formats_data.append({
                'ext': ext,
                'label': label,
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
