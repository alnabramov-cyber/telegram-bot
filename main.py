import os
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.getenv("PORT", "10000"))

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    server.serve_forever()

threading.Thread(target=run_http, daemon=True).start()

while True:
    print("Bot is alive")
    time.sleep(30)
