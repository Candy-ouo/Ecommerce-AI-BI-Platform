"""Flask 应用入口：CORS + 注册全部 Blueprint + 启动。

运行：在 backend/ 目录下 `python app.py`
"""
from flask import Flask, jsonify
from flask_cors import CORS

from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from api import register_blueprints


app = Flask(__name__)
CORS(app)                      # 允许 D 的前端跨域调用
register_blueprints(app)


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
