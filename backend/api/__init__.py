"""Blueprint 集中注册。

Day 1 上午先注册 kpi，其余接口（trend/top/funnel/rfm/recommend/chat）
在 Day 2 各自建好模块后，按同样方式在这里 import + register 即可。
"""
from .kpi import bp as kpi_bp
from .trend import bp as trend_bp
from .top import bp as top_bp
from .funnel import bp as funnel_bp
from .rfm import bp as rfm_bp
from .recommend import bp as recommend_bp
from .chat import bp as chat_bp


def register_blueprints(app):
    app.register_blueprint(kpi_bp)
    app.register_blueprint(trend_bp)
    app.register_blueprint(top_bp)
    app.register_blueprint(funnel_bp)
    app.register_blueprint(rfm_bp)
    app.register_blueprint(recommend_bp)
    app.register_blueprint(chat_bp)
