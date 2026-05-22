from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests
import urllib.parse
import os
import shutil

app = Flask(__name__)
CORS(app)

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
        current_dir = os.path.dirname(os.path.abspath(__file__))
        cookie_source = os.path.join(current_dir, 'cookies.txt')
        cookie_tmp = '/tmp/cookies.txt'

        if os.path.exists(cookie_source):
            shutil.copyfile(cookie_source, cookie_tmp)

        ydl_opts = {
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            # Coba beberapa format audio secara berurutan (anti-crash)
            'format': 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio/best',
            'cookiefile': cookie_tmp if os.path.exists(cookie_tmp) else None,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.youtube.com/',
            },
            # Hindari throttle / bot detection
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'web'],
                }
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'YTAudio Cloud')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)

            # Cari URL audio terbaik
            best_audio_url = None
            best_audio_headers = {}
            formats = info.get('formats', [])

            # 1. Format murni audio, urutkan dari bitrate tertinggi
            audio_formats = [
                f for f in formats
                if f.get('vcodec') == 'none' and f.get('acodec') not in (None, 'none')
            ]

            if audio_formats:
                audio_formats = sorted(audio_formats, key=lambda x: x.get('abr') or x.get('tbr') or 0, reverse=True)
                best = audio_formats[0]
                best_audio_url = best.get('url')
                best_audio_headers = best.get('http_headers', {})
            
            # 2. Fallback: URL dari info utama
            if not best_audio_url:
                best_audio_url = info.get('url')
                best_audio_headers = info.get('http_headers', {})

            # 3. Fallback terakhir: format apapun
            if not best_audio_url and formats:
                best_audio_url = formats[-1].get('url')
                best_audio_headers = formats[-1].get('http_headers', {})

            if not best_audio_url:
                return jsonify({"success": False, "error": "Gagal mengekstrak streaming audio dari video ini"}), 400

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
