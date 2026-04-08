"""
兼容入口：复用 web_ui.py 的统一应用实例。

历史上 app_platform.py 和 web_ui.py 分别维护两套 Flask/SocketIO 入口，
容易造成蓝图注册、路由和会话管理持续分叉。当前文件保留为兼容启动脚本，
真正的应用定义统一收口到 web_ui.py。
"""

from agent_framework.web.web_ui import AgentSession, active_sessions, app, run_server, socketio

__all__ = ["app", "socketio", "active_sessions", "AgentSession", "run_server"]


if __name__ == "__main__":
    print("[compat] app_platform.py now reuses agent_framework.web_ui")
    run_server()
