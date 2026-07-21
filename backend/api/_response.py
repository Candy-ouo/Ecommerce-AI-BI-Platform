"""统一响应格式，对齐 D 前端 api.js 的 {code, message, data} 契约。"""
from flask import jsonify


def ok(data):
    return jsonify({"code": 0, "message": "success", "data": data})


def fail(msg, code=500):
    return jsonify({"code": code, "message": msg, "data": None}), code
