"""pytest 配置 — 注册自定义 markers"""
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "smoke: 冒烟测试 — 快速验证核心功能")
    config.addinivalue_line("markers", "requires_llm: 需要 LLM API Key 的测试")
