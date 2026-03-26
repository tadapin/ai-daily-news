#!/usr/bin/env python3
"""
Daily AI News の docs/ をローカル確認用に配信する。
"""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HOST = "127.0.0.1"
PORT = 8000
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"


class DocsHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DOCS_DIR), **kwargs)


def main():
    server = ThreadingHTTPServer((HOST, PORT), DocsHandler)
    print(f"Serving Daily AI News at http://{HOST}:{PORT}")
    print(f"Document root: {DOCS_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
