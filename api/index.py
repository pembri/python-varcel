from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import yt_dlp
import requests
import urllib.parse

app = Flask(__name__)
# Mengizinkan akses CORS dari domain mana pun
CORS(app)

@app.route('/api', methods=['GET', 'POST'])
def api_handler():
    action = request.args.get('action')
    
    # ==========================================
    # ALUR 1: PROXY DOWNLOAD (Mengunduh Berkas)
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        def generate():
            try:
                r = requests.get(stream_url, stream=True, headers=headers, timeout=30)
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
    # ALUR 2: GENERATE INFO (TANPA COOKIES)
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
        # ---> KONFIGURASI BARU: JALUR NINJA TANPA COOKIES <---
        ydl_opts = {
            'format': 'bestaudio/best',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'nocheckcertificate': True,
            # Maksa Vercel pakai IPv4 (IPv6 sering kena blokir YouTube)
            'source_address': '0.0.0.0',
            # Menyamar jadi klien Android dengan parameter tambahan
            'extractor_args': {
                'youtube': ['client=android', 'player_skip=webpage']
            }
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'YTAudio Cloud')
            thumbnail = info.get('thumbnail', '')
            duration = info.get('duration', 0)
            best_audio_url = info.get('url')
            
            if not best_audio_url:
                return jsonify({"success": False, "error": "Gagal mengekstrak streaming audio"}), 400
            
            base_api_url = "https://python-varcel.vercel.app/api"
            
            formats_data = []
            supported_exts = [
                {'ext': 'mp3', 'label': 'MP3 (Audio Populer)'},
                {'ext': 'wav', 'label': 'WAV (Kualitas Tinggi)'},
                {'ext': 'm4a', 'label': 'M4A (Original AAC)'}
            ]
            
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
