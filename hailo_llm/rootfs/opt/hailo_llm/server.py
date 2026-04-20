from flask import Flask, jsonify
import os
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "ok", "hailo": os.path.exists("/dev/hailo0")})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099)