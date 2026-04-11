#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单的 HTTP 服务器启动脚本
运行此脚本将自动编译项目并启动本地服务器，然后在浏览器中打开网页
"""

import http.server
import socketserver
import webbrowser
import os
import time
import threading
import subprocess
import sys
import io
import errno

# 修复 Windows 控制台输出编码问题
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 配置参数
PORT = 1125  # 服务器端口
DIRECTORY = "docs"  # 要服务的目录（构建后的文件夹）


class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    """自定义请求处理器，指定服务目录"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)
    
    def log_message(self, format, *args):
        """自定义日志输出格式，使其更简洁"""
        print(f"[访问] {args[0]} - {args[1]}")


def open_browser(url, delay=1.5):
    """
    延迟打开浏览器
    :param url: 要打开的网址
    :param delay: 延迟秒数
    """
    time.sleep(delay)
    print(f"\n🚀 正在浏览器中打开: {url}")
    webbrowser.open(url)


def is_address_in_use_error(error):
    return error.errno in {errno.EADDRINUSE, 10048}


def build_project():
    """编译项目"""
    print("\n" + "=" * 60)
    print("📦 开始编译项目...")
    print("=" * 60)
    
    # 检查是否存在 node_modules
    if not os.path.exists("node_modules"):
        print("❌ 错误: 未找到 node_modules 目录")
        print("💡 请先运行: npm install 或 yarn install")
        return False
    
    # 检查 vite 是否存在
    vite_path = os.path.join("node_modules", "vite", "bin", "vite.js")
    if not os.path.exists(vite_path):
        print("❌ 错误: 未找到 Vite")
        print("💡 请先运行: npm install 或 yarn install")
        return False
    
    try:
        # 使用 node 运行 vite build
        print("\n⏳ 正在编译，请稍候...\n")
        
        # Windows 系统使用不同的方式执行命令
        if sys.platform == "win32":
            result = subprocess.run(
                ["node", vite_path, "build"],
                cwd=os.getcwd(),
                capture_output=False,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
        else:
            result = subprocess.run(
                ["node", vite_path, "build"],
                cwd=os.getcwd(),
                capture_output=False,
                text=True
            )
        
        if result.returncode == 0:
            print("\n" + "=" * 60)
            print("✅ 项目编译成功！")
            print("=" * 60 + "\n")
            return True
        else:
            print(f"\n❌ 编译失败，退出码: {result.returncode}")
            return False
            
    except FileNotFoundError:
        print("❌ 错误: 未找到 Node.js")
        print("💡 请确保已安装 Node.js 并添加到系统环境变量")
        return False
    except Exception as e:
        print(f"❌ 编译过程中出现错误: {e}")
        return False


def start_server():
    """启动 HTTP 服务器"""
    
    # 检查 docs 目录是否已存在
    docs_exists = os.path.exists(DIRECTORY)
    
    if docs_exists:
        print("\n" + "=" * 60)
        print(f"📁 检测到已存在的 {DIRECTORY} 目录")
        print("✅ 跳过编译，使用现有文件启动服务器...")
        print("=" * 60)
    else:
        # docs 不存在，必须编译
        if not build_project():
            print("\n❌ 编译失败，无法启动服务器")
            return
    
    # 最后检查目录是否存在
    if not os.path.exists(DIRECTORY):
        print(f"\n❌ 错误: 目录 '{DIRECTORY}' 不存在！")
        print(f"💡 提示: 需要先编译项目生成 docs 目录")
        return
    
    # 创建服务器
    Handler = MyHTTPRequestHandler
    
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            url = f"http://localhost:{PORT}"
            
            print("=" * 60)
            print(f"✨ 数据平台服务器启动成功！")
            print(f"📁 服务目录: {os.path.abspath(DIRECTORY)}")
            print(f"🌐 访问地址: {url}")
            print(f"⚡ 按 Ctrl+C 停止服务器")
            print("=" * 60)
            
            # 在新线程中延迟打开浏览器
            browser_thread = threading.Thread(target=open_browser, args=(url,))
            browser_thread.daemon = True
            browser_thread.start()
            
            # 启动服务器（阻塞）
            httpd.serve_forever()
            
    except OSError as e:
        if is_address_in_use_error(e):
            print(f"❌ 错误: 端口 {PORT} 已被占用！")
            print(f"💡 解决方案:")
            print(f"   1. 关闭占用端口的程序")
            print(f"   2. 或修改脚本中的 PORT 变量为其他端口号")
        else:
            print(f"❌ 错误: {e}")
    except KeyboardInterrupt:
        print("\n\n👋 服务器已停止")


if __name__ == "__main__":
    start_server()
