#!/usr/bin/env python3
"""Local review server for census card FIO verification."""

import argparse
import csv
import json
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

IMAGE_DIR: Path = Path(".")
CSV_PATH: Path = Path(".")
HTML_PATH = Path(__file__).parent / "review.html"
PORT = 8080


def load_csv():
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


class ReviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_PATH.read_bytes())

        elif parsed.path == "/api/data":
            rows = load_csv()
            for r in rows:
                r["not_jewish"] = r.get("not_jewish", "") == "true"
                r["_edited"] = False
                r["_orig_name"] = r.get("name", "")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(rows, ensure_ascii=False).encode("utf-8"))

        elif parsed.path.startswith("/img/"):
            filename = parsed.path[5:]
            img_path = IMAGE_DIR / filename
            if img_path.exists() and img_path.suffix.lower() in (".jpg", ".jpeg", ".png"):
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                self.wfile.write(img_path.read_bytes())
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/save":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            data = json.loads(body)

            csv_fields = [
                "filename", "name", "confidence", "nationality", "notes", "not_jewish",
            ]
            rows = []
            for d in data:
                row = {k: d.get(k, "") for k in csv_fields}
                row["not_jewish"] = "true" if d.get("not_jewish") else ""
                rows.append(row)

            with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=csv_fields)
                writer.writeheader()
                writer.writerows(rows)

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": True, "count": len(rows)}).encode("utf-8"))
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        pass


def main():
    global IMAGE_DIR, CSV_PATH, PORT

    parser = argparse.ArgumentParser(description="Census review server")
    parser.add_argument(
        "--source", type=Path,
        default=Path("/Users/michaelak/Documents/Харьков 1926/582-1-1433"),
        help="Directory containing source JPG images",
    )
    parser.add_argument(
        "--csv", type=Path,
        default=Path(__file__).parent / "census_output" / "review.csv",
        help="Path to review.csv",
    )
    parser.add_argument("--port", type=int, default=8080, help="Server port")
    args = parser.parse_args()

    IMAGE_DIR = args.source.resolve()
    CSV_PATH = args.csv.resolve()
    PORT = args.port

    if not IMAGE_DIR.is_dir():
        parser.error(f"Source directory not found: {IMAGE_DIR}")
    if not CSV_PATH.exists():
        parser.error(f"CSV file not found: {CSV_PATH}")

    print(f"Census Review Server")
    print(f"  CSV:    {CSV_PATH}")
    print(f"  Images: {IMAGE_DIR}")
    print(f"  HTML:   {HTML_PATH}")
    print(f"  URL:    http://localhost:{PORT}")
    print(f"\nPress Ctrl+C to stop\n")

    server = HTTPServer(("", PORT), ReviewHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.server_close()


if __name__ == "__main__":
    main()
