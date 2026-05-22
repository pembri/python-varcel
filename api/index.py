from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)

# IZINKAN SEMUA DOMAIN
CORS(app)

@app.route("/api")
def api():

    return jsonify({
        "status": "online",
        "message": "Halo dari Python Vercel",
        "creator": "Pembri"
    })

handler = app
