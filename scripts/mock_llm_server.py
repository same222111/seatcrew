"""Tiny OpenAI-compatible mock server for demos/E2E tests without a real key.
Run: python scripts/mock_llm_server.py 18080  -> set provider 'custom' base URL to http://127.0.0.1:18080/v1"""
import json, re, sys
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        b = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); sys_p = b["messages"][0]["content"]; user = b["messages"][-1]["content"]
        if "pong" in user: txt = "pong"
        else:
            labels = re.findall(r"'([a-z0-9]+)'", sys_p.split("one of", 1)[-1]); lab = labels[0] if labels else "neutral"
            txt = json.dumps({"label": lab, "reason": f"mock model says {lab}"})
        out = json.dumps({"choices": [{"message": {"content": txt}}], "model": b.get("model")}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(out)
if __name__ == "__main__": HTTPServer(("127.0.0.1", int(sys.argv[1]) if len(sys.argv) > 1 else 18080), H).serve_forever()
