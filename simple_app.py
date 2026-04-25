"""
简洁版智能工作台
左侧：5个核心功能模块导航
右侧：功能页面嵌入显示
"""

import sys
from pathlib import Path

# 添加 src 到路径
repo_root = Path(__file__).parent
src_path = repo_root / "src"
sys.path.insert(0, str(src_path))

from flask import Flask, render_template, send_file
from flask_socketio import SocketIO

# 导入原系统的 web_ui 模块
from agent_framework.web import web_ui

# 使用原系统的 Flask app
app = web_ui.app
socketio = web_ui.socketio

# 直接替换原来的 root_home 函数
def simple_home():
    """简洁主页"""
    return render_template('simple_home.html')

# 替换视图函数
app.view_functions['root_home'] = simple_home

# 添加主页图片路由
@app.route('/主页.png')
def home_image():
    """提供主页图片"""
    image_path = repo_root / '主页.png'
    if image_path.exists():
        return send_file(image_path, mimetype='image/png')
    return "Image not found", 404


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 简洁版智能工作台启动中...")
    print("=" * 60)
    print("\n📍 访问地址：")
    print("   http://localhost:5001")
    print("\n💡 功能模块：")
    print("   - 风场选址")
    print("   - 智能工单")
    print("   - 智能值守")
    print("   - 电力交易")
    print("   - 智导助手")
    print("\n按 Ctrl+C 停止服务")
    print("=" * 60)
    print()

    socketio.run(app, host='0.0.0.0', port=5001, debug=True, allow_unsafe_werkzeug=True)
