#!/usr/bin/env python3
"""
简单启动脚本 - 使用Python内置HTTP服务器
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
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    return None

def main():
    # 切换到前端目录
    frontend_dir = Path(__file__).parent
    os.chdir(frontend_dir)
    
    # 查找可用端口
    port = find_available_port(8080)
    if not port:
        print("❌ 无法找到可用端口")
        return
    
    print("🚀 启动AI助手前端界面")
    print("=" * 50)
    print(f"📁 服务目录: {frontend_dir}")
    print(f"📍 主界面: http://localhost:{port}")
    print(f"📍 演示页面: http://localhost:{port}/demo.html")
    print(f"🔧 后端API: http://localhost:8000")
    print("=" * 50)
    print("💡 使用说明:")
    print("   1. 确保后端API已启动")
    print("   2. 浏览器会自动打开主界面")
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
        with socketserver.TCPServer(("", port), CORSRequestHandler) as httpd:
            print(f"✅ 服务器启动成功，端口: {port}")
            
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
