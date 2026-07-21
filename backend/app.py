"""Flask 应用入口：CORS + 注册全部 Blueprint + 启动定时任务 + 启动。

运行：在 backend/ 目录下 `python app.py`
"""
from flask import Flask
from flask_cors import CORS

from api._response import ok
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG
from api import register_blueprints
from scheduler import start_scheduler


app = Flask(__name__)
CORS(app)                      # 允许 D 的前端跨域调用
register_blueprints(app)


@app.route("/health")
def health():
    return ok({"status": "ok"})


if __name__ == "__main__":
    start_scheduler()           # 启动每日 8:00 晨报定时任务
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
