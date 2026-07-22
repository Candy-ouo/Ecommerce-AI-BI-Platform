"""Blueprint 集中注册。"""
from .kpi import bp as kpi_bp
from .trend import bp as trend_bp
from .top import bp as top_bp
from .funnel import bp as funnel_bp
from .rfm import bp as rfm_bp
from .recommend import bp as recommend_bp
from .chat import bp as chat_bp
from .report import bp as report_bp
from .agent import bp as agent_bp


def register_blueprints(app):
    app.register_blueprint(kpi_bp)
    app.register_blueprint(trend_bp)
    app.register_blueprint(top_bp)
    app.register_blueprint(funnel_bp)
    app.register_blueprint(rfm_bp)
    app.register_blueprint(recommend_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(agent_bp)
