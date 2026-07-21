"""Flask 应用入口：CORS + API 鉴权 + 注册全部 Blueprint + 启动定时任务 + 启动。

运行：在 backend/ 目录下 `python app.py`
"""
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

from api._response import ok
from config import FLASK_HOST, FLASK_PORT, FLASK_DEBUG, API_TOKEN
from api import register_blueprints
from scheduler import start_scheduler

logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)                      # 允许 D 的前端跨域调用

# ── 注册蓝图（含异常保护，避免导入环节静默失败）────
try:
    register_blueprints(app)
except Exception as e:
    logger.exception("Blueprint 注册失败: %s", e)


# ── API 鉴权（全局 before_request）──────────────────
# 若未配置 API_TOKEN，则放行所有请求（向后兼容）。
# 配置后，所有 /api/* 请求需携带 Authorization: Bearer <token>。
@app.before_request
def _check_auth():
    if not API_TOKEN:
        return None                        # 鉴权关闭

    if request.method == "OPTIONS":
        return None                        # CORS 预检放行

    path = request.path
    if not path.startswith("/api/"):
        return None                        # /health 等非 API 路由放行

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({
            "code": 401,
            "message": "Missing or invalid Authorization header. Use: Bearer <token>",
            "data": None,
        }), 401

    token = auth_header[7:]
    if token != API_TOKEN:
        logger.warning("Unauthorized API access from %s", request.remote_addr)
        return jsonify({
            "code": 403,
            "message": "Invalid API token",
            "data": None,
        }), 403

    return None                            # 鉴权通过


@app.route("/health")
def health():
    return ok({"status": "ok"})


if __name__ == "__main__":
    start_scheduler()           # 启动每日 8:00 晨报定时任务
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=FLASK_DEBUG)
