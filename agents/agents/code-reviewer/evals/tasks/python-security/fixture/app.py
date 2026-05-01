"""Flask API アプリケーション — ユーザー管理"""

from flask import Flask, request, jsonify
import subprocess
import sqlite3

app = Flask(__name__)

DB_PATH = "users.db"


@app.route("/users")
def get_users():
    name = request.args.get("name", "")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute(f"SELECT * FROM users WHERE name = '{name}'")
    results = cursor.fetchall()
    conn.close()
    return jsonify(results)


@app.route("/health")
def health_check():
    host = request.args.get("host", "localhost")
    result = subprocess.run(f"ping -c 1 {host}", shell=True, capture_output=True)
    return jsonify({"status": "ok", "ping": result.stdout.decode()})


@app.route("/files")
def read_file():
    filename = request.args.get("path", "")
    with open(filename) as f:
        return f.read()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
