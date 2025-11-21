#!/usr/bin/env python3
"""
前端HTTP服务器 - 使用Python内置HTTP服务器
"""

import http.server
import socketserver
import webbrowser
import os
import sys
from pathlib import Path

def find_available_port(start_port=8080):
    """查找可用端口"""
    import socket
    for port in range(start_port, start_port + 100):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
                return port
        except OSError:
            continue
    return None

def get_local_ip():
    """获取本机IP地址"""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

def main():
    # 切换到前端目录
    frontend_dir = Path(__file__).parent
    os.chdir(frontend_dir)

    # 使用固定端口 8090（已在 Windows 做了端口转发）
    port = 8090

    local_ip = get_local_ip()

    print("🚀 启动AI助手前端界面")
    print("=" * 50)
    print(f"📁 服务目录: {frontend_dir}")
    print(f"📍 访问地址: http://0.0.0.0:{port}")
    print(f"📍 本机IP: http://{local_ip}:{port}")
    print(f"🔧 后端API: http://localhost:8000")
    print("=" * 50)
    print("💡 使用说明:")
    print("   1. 确保后端API已启动")
    print(f"   2. 在浏览器中访问 http://{local_ip}:{port}")
    print("   3. 开始与AI助手对话")
    print("   4. 按 Ctrl+C 停止服务器")
    print("=" * 50)

    # 启动服务器
    handler = http.server.SimpleHTTPRequestHandler

    # 添加CORS支持
    class CORSRequestHandler(handler):
        def end_headers(self):
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            super().end_headers()

        def do_OPTIONS(self):
            self.send_response(200)
            self.end_headers()

    try:
        with socketserver.TCPServer(("0.0.0.0", port), CORSRequestHandler) as httpd:
            print(f"✅ 服务器启动成功，监听: 0.0.0.0:{port}")

            # 提示用户手动打开浏览器
            print("🌐 请在浏览器中打开上述地址")

            print("\n等待连接...")
            httpd.serve_forever()

    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
    except Exception as e:
        print(f"❌ 启动失败: {e}")

if __name__ == "__main__":
    main()
