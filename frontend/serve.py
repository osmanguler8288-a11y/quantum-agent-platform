#!/usr/bin/env python3
"""Quantum Agent Platform 前端静态服务（SPA：history 路由回退到 index.html）。

用 Python 标准库 http.server 托管 frontend/dist，无需 nginx。
端口从环境变量 PORT 读取，默认 8000（systemd 里由 Environment=PORT 指定）。
"""
import os
import http.server
import socketserver

PORT = int(os.environ.get("PORT", "8000"))
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dist")


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        # history 路由（/chat、/auth 等）无对应静态文件时回退到 index.html
        if not os.path.isfile(self.translate_path(self.path)):
            self.path = "/index.html"
        super().do_GET()


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReusableTCPServer(("0.0.0.0", PORT), SPAHandler) as httpd:
        print(f"QAP frontend serving {ROOT} on 0.0.0.0:{PORT}", flush=True)
        httpd.serve_forever()
