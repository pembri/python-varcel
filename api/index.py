from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import requests
import urllib.parse
import json
import re
import os

app = Flask(__name__)
CORS(app)

HEADERS = {
    'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip',
    'Content-Type': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
    'X-YouTube-Client-Name': '3',
    'X-YouTube-Client-Version': '19.09.37',
}

def extract_video_id(url):
    patterns = [
        r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None

def get_video_info(video_id):
    payload = {
        "context": {
            "client": {
                "clientName": "ANDROID",
                "clientVersion": "19.09.37",
                "androidSdkVersion": 30,
                "userAgent": "com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip",
                "hl": "en",
                "timeZone": "UTC",
                "utcOffsetMinutes": 0
            }
        },
        "videoId": video_id,
        "params": "8AEB",
        "contentCheckOk": True,
        "racyCheckOk": True
    }

    resp = requests.post(
        'https://www.youtube.com/youtubei/v1/player?key=AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8',
        headers=HEADERS,
        json=payload,
        timeout=15
    )
    return resp.json()

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
            'User-Agent': 'com.google.android.youtube/19.09.37 (Linux; U; Android 11) gzip',
            'Referer': 'https://www.youtube.com/',
        }

        def generate():
            try:
                r = requests.get(stream_url, stream=True, headers=dl_headers, timeout=60)
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

        response_headers = {
            'Content-Disposition': f'attachment; filename="{safe_title}.{ext}"',
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
        video_id = extract_video_id(url)
        if not video_id:
            return jsonify({"success": False, "error": "URL YouTube tidak valid"}), 400

        data = get_video_info(video_id)

        # Cek error dari YouTube
        playability = data.get('playabilityStatus', {})
        if playability.get('status') not in ('OK', None):
            reason = playability.get('reason', 'Video tidak bisa diakses')
            return jsonify({"success": False, "error": reason}), 400

        # Ambil metadata
        details = data.get('videoDetails', {})
        title = details.get('title', 'YTAudio Cloud')
        duration = int(details.get('lengthSeconds', 0))
        thumbnails = details.get('thumbnail', {}).get('thumbnails', [])
        thumbnail = thumbnails[-1]['url'] if thumbnails else ''

        # Ambil stream audio terbaik
        streaming = data.get('streamingData', {})
        formats = streaming.get('adaptiveFormats', []) + streaming.get('formats', [])

        # Filter hanya audio (tidak ada video)
        audio_formats = [
            f for f in formats
            if f.get('mimeType', '').startswith('audio/')
        ]

        if not audio_formats:
            # Fallback: semua format
            audio_formats = formats

        if not audio_formats:
            return jsonify({"success": False, "error": "Tidak ada stream audio tersedia"}), 400

        # Urutkan berdasarkan bitrate tertinggi
        audio_formats.sort(key=lambda x: x.get('bitrate', 0), reverse=True)
        best = audio_formats[0]
        best_audio_url = best.get('url')

        if not best_audio_url:
            return jsonify({"success": False, "error": "URL stream tidak ditemukan"}), 400

        base_api_url = "https://python-varcel.vercel.app/api"

        supported_exts = [
            {'ext': 'mp3', 'label': 'MP3 (Audio Populer)'},
            {'ext': 'wav', 'label': 'WAV (Kualitas Tinggi)'},
            {'ext': 'm4a', 'label': 'M4A (Original AAC)'}
        ]

        formats_data = []
        for item in supported_exts:
            ext = item['ext']
            encoded_title = urllib.parse.quote(title)
            encoded_url = urllib.parse.quote(best_audio_url)
            download_link = f"{base_api_url}?action=download&ext={ext}&title={encoded_title}&url={encoded_url}"
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
