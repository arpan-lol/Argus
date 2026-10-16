import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse
from .core import Engine, JsonIngestor
from .graph import LocalGraph, FalkorGraph
from .store import Store


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=".data/engine.sqlite3")
    parser.add_argument("--graph", choices=["local", "falkordb"], default="local")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("ingest")
    ingest.add_argument("path")
    query = commands.add_parser("query")
    query.add_argument("question")
    query.add_argument("--limit", type=int, default=5)
    commands.add_parser("inspect")
    serve = commands.add_parser("serve")
    serve.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    store = Store(args.db)
    engine = Engine(store, FalkorGraph() if args.graph == "falkordb" else LocalGraph(store))
    if args.command == "ingest":
        output = engine.ingest(JsonIngestor().load(args.path))
    elif args.command == "query":
        output = engine.query(args.question, args.limit)
    elif args.command == "inspect":
        output = {key: store.records(key) for key in ["documents", "evidence", "claims"]}
        output["runs"] = store.runs()
        output["capabilities"] = engine.capabilities()
    else:
        class Handler(BaseHTTPRequestHandler):
            def respond(self, status, value):
                data = json.dumps(value, ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                path = urlparse(self.path).path
                if path == "/health":
                    capabilities = engine.capabilities()
                    self.respond(200 if capabilities["graph"]["available"] else 503, {"status": "ready" if capabilities["graph"]["available"] else "degraded", "graph": args.graph, "capabilities": capabilities})
                elif path == "/capabilities":
                    self.respond(200, engine.capabilities())
                elif path == "/runs":
                    self.respond(200, store.runs())
                elif path.startswith("/runs/"):
                    self.respond(200, store.events(path.split("/")[-1]))
                elif path in {"/documents", "/evidence", "/claims"}:
                    self.respond(200, store.records(path[1:], limit=1000))
                else:
                    self.respond(404, {"error": "Unknown endpoint"})

            def do_POST(self):
                if self.path != "/query":
                    self.respond(404, {"error": "Unknown endpoint"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 100000:
                        raise ValueError("Request body must contain 1–100000 bytes")
                    body = json.loads(self.rfile.read(length))
                    self.respond(200, engine.query(body.get("question"), body.get("limit", 5), body.get("expand", True)))
                except (ValueError, TypeError, AttributeError) as exc:
                    self.respond(400, {"error": str(exc), "run_id": getattr(exc, "run_id", None)})
                except Exception as exc:
                    self.respond(500, {"error": "Processing failed; inspect run ledger", "run_id": getattr(exc, "run_id", None)})
        print(f"Inspection API: http://127.0.0.1:{args.port}")
        HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
        return
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
