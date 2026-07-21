"""基础 API 鉴权（Bearer Token）。

用法：在蓝图或路由上用 @require_auth 装饰。
若未配置 API_TOKEN，则放行所有请求（向后兼容）。
"""
import os
import logging
from functools import wraps
from flask import request, jsonify

logger = logging.getLogger(__name__)

_API_TOKEN = os.getenv("API_TOKEN", "")


def require_auth(f):
    """装饰器：验证 Authorization: Bearer <token> 头。

    若 API_TOKEN 未配置（空字符串），则鉴权关闭，常用于开发阶段。
    生产部署时在 .env 中设置 API_TOKEN=your-secret 即可启用。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _API_TOKEN:
            # 鉴权关闭，向后兼容
            return f(*args, **kwargs)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({
                "code": 401,
                "message": "Missing or invalid Authorization header. Use: Bearer <token>",
                "data": None,
            }), 401

        token = auth_header[7:]
        if token != _API_TOKEN:
            logger.warning("Unauthorized access attempt from %s", request.remote_addr)
            return jsonify({
                "code": 403,
                "message": "Invalid API token",
                "data": None,
            }), 403

        return f(*args, **kwargs)
    return decorated
