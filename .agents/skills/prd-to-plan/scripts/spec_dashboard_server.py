from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class SpecRecord:
    name: str
    version: str
    feature: str
    path: str
    stage: str
    language: str
    updated_at: str | None
    error: str | None = None


def _iso_mtime(path: Path) -> str | None:
    if not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError("spec.json 顶层必须是对象")
    return data


def discover_specs(spec_root: Path) -> list[SpecRecord]:
    if not spec_root.exists():
        return []

    records: list[SpecRecord] = []
    for spec_json in sorted(spec_root.glob("*/*/spec.json")):
        spec_dir = spec_json.parent
        version = spec_dir.parent.name
        feature = spec_dir.name
        name = f"{version}/{feature}"
        try:
            data = _read_json(spec_json)
            stage = str(data.get("stage", "unknown"))
            language = str(data.get("language", ""))
            error = None
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            stage = "invalid"
            language = ""
            error = str(exc)

        records.append(
            SpecRecord(
                name=name,
                version=version,
                feature=feature,
                path=str(spec_dir),
                stage=stage,
                language=language,
                updated_at=_iso_mtime(spec_json),
                error=error,
            )
        )
    return records


def build_summary(records: list[SpecRecord]) -> dict[str, Any]:
    stages: dict[str, int] = {}
    for record in records:
        stages[record.stage] = stages.get(record.stage, 0) + 1
    return {
        "total": len(records),
        "stages": stages,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def build_detail(spec_root: Path, name: str) -> dict[str, Any] | None:
    spec_dir = spec_root / Path(name)
    spec_json = spec_dir / "spec.json"
    if not spec_json.exists():
        return None

    data = _read_json(spec_json)
    files: dict[str, dict[str, Any]] = {}
    for filename in ("requirements.md", "design.md", "tasks.md"):
        file_path = spec_dir / filename
        files[filename] = {
            "exists": file_path.exists(),
            "updated_at": _iso_mtime(file_path),
            "size": file_path.stat().st_size if file_path.exists() else 0,
        }
    return {"name": name, "path": str(spec_dir), "spec": data, "files": files}


def build_logs(spec_root: Path, name: str) -> dict[str, Any] | None:
    detail = build_detail(spec_root, name)
    if detail is None:
        return None

    spec = detail["spec"]
    verification = spec.get("verification", [])
    if not isinstance(verification, list):
        verification = []

    events: list[dict[str, Any]] = []
    for filename, meta in detail["files"].items():
        if meta["exists"]:
            events.append(
                {
                    "type": "file",
                    "name": filename,
                    "updated_at": meta["updated_at"],
                    "size": meta["size"],
                }
            )
    for item in verification:
        if isinstance(item, dict):
            events.append({"type": "verification", **item})
    return {"name": name, "events": events}


DASHBOARD_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>太初规格进度</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 32px; background: #111; color: #f5f5f5; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; }
    th, td { border: 1px solid #444; padding: 8px 10px; text-align: left; }
    th { background: #222; }
    code { color: #9ee493; }
  </style>
</head>
<body>
  <h1>太初规格进度</h1>
  <p id="summary">正在读取规格...</p>
  <table>
    <thead><tr><th>规格</th><th>阶段</th><th>语言</th><th>更新时间</th><th>路径</th></tr></thead>
    <tbody id="rows"></tbody>
  </table>
  <script>
    async function load() {
      const [summary, specs] = await Promise.all([
        fetch('/api/summary').then((r) => r.json()),
        fetch('/api/specs').then((r) => r.json()),
      ]);
      document.getElementById('summary').textContent =
        `共 ${summary.total} 个规格，阶段统计：${JSON.stringify(summary.stages)}`;
      document.getElementById('rows').innerHTML = specs.map((spec) => `
        <tr>
          <td>${spec.name}</td>
          <td>${spec.stage}</td>
          <td>${spec.language || '-'}</td>
          <td>${spec.updated_at || '-'}</td>
          <td><code>${spec.path}</code></td>
        </tr>
      `).join('');
    }
    load().catch((error) => {
      document.getElementById('summary').textContent = `读取失败：${error}`;
    });
  </script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    spec_root: Path

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        records = discover_specs(self.spec_root)

        if path in ("/", "/dashboard.html"):
            self._send_html(DASHBOARD_HTML)
            return
        if path == "/api/summary":
            self._send_json(build_summary(records))
            return
        if path == "/api/specs":
            self._send_json([record.__dict__ for record in records])
            return
        if path.startswith("/api/specs/"):
            name = unquote(path.removeprefix("/api/specs/"))
            detail = build_detail(self.spec_root, name)
            if detail is None:
                self._send_json({"error": "规格不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(detail)
            return
        if path.startswith("/api/logs/"):
            name = unquote(path.removeprefix("/api/logs/"))
            logs = build_logs(self.spec_root, name)
            if logs is None:
                self._send_json({"error": "规格不存在"}, HTTPStatus.NOT_FOUND)
            else:
                self._send_json(logs)
            return

        self._send_json({"error": "接口不存在"}, HTTPStatus.NOT_FOUND)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[spec-dashboard] {self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="太初规格进度 Dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8686)
    parser.add_argument("--spec-root", default=".kiro/specs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spec_root = Path(args.spec_root)
    handler = type("ConfiguredDashboardHandler", (DashboardHandler,), {})
    handler.spec_root = spec_root
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"太初规格 Dashboard 已启动：http://{args.host}:{args.port}/dashboard.html")
    print(f"规格目录：{spec_root.resolve()}")
    server.serve_forever()


if __name__ == "__main__":
    main()
