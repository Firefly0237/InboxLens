from __future__ import annotations

import contextlib
import io
import webbrowser
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from inbox_lens.onboarding import (
    BOOL_KEYS,
    DEFAULT_ENV,
    SECRET_KEYS,
    masked,
    read_env_values,
    run_doctor,
    settings_from_values,
    update_env_from_form,
)
from inbox_lens.pipeline import run_digest, send_test_email
from inbox_lens.sample import render_sample_digest
from inbox_lens.storage import Repository


def serve_console(host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        raise ValueError("Use 127.0.0.1, localhost, or 0.0.0.0 for containerized deployments.")

    class Handler(_ConsoleHandler):
        pass

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{server.server_port}/"
    print(f"InboxLens console is running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nInboxLens console stopped.")
    finally:
        server.server_close()


class _ConsoleHandler(BaseHTTPRequestHandler):
    server_version = "InboxLensConsole/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(_render_dashboard(_message_from_query(parsed.query)))
            return
        if parsed.path == "/preview":
            self._send_preview()
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        form = self._read_form()
        try:
            if parsed.path == "/save-config":
                update_env_from_form(form)
                self._redirect("配置已保存。")
                return
            if parsed.path == "/action/init-db":
                settings = _fresh_settings()
                Repository(settings.database_path).init_schema()
                self._redirect("数据库已初始化。")
                return
            if parsed.path == "/action/render-sample":
                _render_sample_via_cli()
                self._redirect("样例简报已生成。")
                return
            if parsed.path == "/action/dry-run":
                settings = _fresh_settings()
                limit = _optional_int(form.get("limit"), 10)
                digest = _run_silently(lambda: run_digest(settings, dry_run=True, limit=limit))
                self._redirect(f"试跑完成。{_digest_summary(digest)}")
                return
            if parsed.path == "/action/send-test":
                settings = _fresh_settings()
                send_test_email(settings)
                self._redirect("SMTP 测试邮件已发送。")
                return
            if parsed.path == "/action/run":
                settings = _fresh_settings()
                digest = run_digest(settings)
                self._redirect(f"正式简报已发送。{_digest_summary(digest)}")
                return
            if parsed.path == "/action/auth-check":
                settings = _fresh_settings()
                checks = run_doctor(settings, network=False, auth=True)
                auth_checks = [check for check in checks if check.name.endswith("auth")]
                self._redirect(_auth_summary(auth_checks), level="ok" if all(c.status == "ok" for c in auth_checks) else "error")
                return
        except Exception as exc:
            self._redirect(f"操作失败：{exc}", level="error")
            return
        self.send_error(404, "Not found")

    def log_message(self, format: str, *args) -> None:
        return

    def _read_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def _send_html(self, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_preview(self) -> None:
        preview = Path("out/last_digest.html")
        fallback = Path("out/sample_digest.html")
        target = preview if preview.exists() else fallback
        if not target.exists():
            self.send_error(404, "No preview generated yet")
            return
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, message: str, level: str = "ok") -> None:
        from urllib.parse import quote

        self.send_response(303)
        self.send_header("Location", f"/?message={quote(message)}&level={level}")
        self.end_headers()


def _render_dashboard(message: tuple[str, str] | None = None) -> str:
    values = read_env_values()
    settings = settings_from_values(values)
    checks = run_doctor(settings, network=False)
    runs = Repository(settings.database_path).recent_runs(8)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InboxLens Console</title>
  <style>{_CSS}</style>
</head>
<body>
  <main class="shell">
    <header class="top">
      <div>
        <h1>InboxLens 控制台</h1>
        <p>本地配置、诊断、预览和运行入口。</p>
      </div>
      <a class="link" href="/preview" target="_blank">打开简报预览</a>
    </header>
    {_message_html(message)}
    <section class="grid">
      <article class="panel">
        <h2>环境诊断</h2>
        <div class="checks">{''.join(_check_html(check) for check in checks)}</div>
      </article>
      <article class="panel">
        <h2>快捷操作</h2>
        <div class="actions">
          {_action_form('/action/init-db', '初始化数据库')}
          {_action_form('/action/render-sample', '生成样例简报')}
          {_action_form('/action/auth-check', '验证 IMAP / SMTP 登录')}
          {_dry_run_form()}
          {_action_form('/action/send-test', '发送 SMTP 测试邮件')}
          {_action_form('/action/run', '发送正式简报', danger=True)}
        </div>
      </article>
    </section>
    <section class="panel">
      <h2>配置</h2>
      {_config_form(values)}
    </section>
    <section class="panel">
      <h2>最近运行</h2>
      {_runs_table(runs)}
    </section>
  </main>
</body>
</html>"""


def _config_form(values: dict[str, str]) -> str:
    fields = [
        ("IMAP_HOST", "IMAP 主机"),
        ("IMAP_PORT", "IMAP 端口"),
        ("IMAP_USER", "源邮箱账号"),
        ("IMAP_PASSWORD", "源邮箱授权码"),
        ("IMAP_FOLDER", "邮箱目录"),
        ("SMTP_HOST", "SMTP 主机"),
        ("SMTP_PORT", "SMTP 端口"),
        ("SMTP_USER", "发送邮箱账号"),
        ("SMTP_PASSWORD", "发送邮箱授权码"),
        ("SMTP_FROM", "发件人地址"),
        ("DIGEST_TO", "简报接收地址"),
        ("DATABASE_PATH", "数据库路径"),
        ("INBOX_LENS_TIMEZONE", "时区"),
        ("USER_RULES_PATH", "个人规则路径"),
        ("LLM_BASE_URL", "LLM 接口地址"),
        ("LLM_API_KEY", "LLM API Key"),
        ("LLM_MODEL", "LLM 模型"),
    ]
    bools = [
        ("SMTP_USE_SSL", "SMTP SSL"),
        ("SMTP_STARTTLS", "SMTP STARTTLS"),
        ("SEND_EMPTY_DIGEST", "发送空简报"),
        ("SEND_FAILURE_EMAIL", "失败时发邮件"),
        ("LLM_ENABLED", "启用 LLM"),
        ("LLM_JSON_MODE", "LLM JSON mode"),
    ]
    field_html = []
    for key, label in fields:
        field_type = "password" if key in SECRET_KEYS else "text"
        value = "" if key in SECRET_KEYS else values.get(key, DEFAULT_ENV.get(key, ""))
        placeholder = masked(values.get(key, "")) if key in SECRET_KEYS else ""
        field_html.append(
            f"<label><span>{escape(label)}</span>"
            f"<input name=\"{escape(key)}\" type=\"{field_type}\" value=\"{escape(value)}\" placeholder=\"{escape(placeholder)}\"></label>"
        )
    bool_html = []
    for key, label in bools:
        checked = " checked" if values.get(key, DEFAULT_ENV.get(key, "false")).lower() in {"1", "true", "yes", "on"} else ""
        bool_html.append(f"<label class=\"check\"><input name=\"{escape(key)}\" type=\"checkbox\"{checked}> {escape(label)}</label>")
    return (
        "<form class=\"config\" method=\"post\" action=\"/save-config\">"
        "<div class=\"form-grid\">"
        + "".join(field_html)
        + "</div><div class=\"bool-grid\">"
        + "".join(bool_html)
        + "</div><button type=\"submit\">保存配置</button></form>"
    )


def _runs_table(runs: list[dict[str, object]]) -> str:
    if not runs:
        return "<p class=\"muted\">暂无运行记录。</p>"
    rows = []
    for run in runs:
        mail_count = run.get("mail_count", 0)
        annotated = f"{mail_count}" + (" (空窗口)" if mail_count == 0 and run.get("status") in {"success", "empty"} else "")
        rows.append(
            "<tr>"
            f"<td>#{escape(str(run['id']))}</td>"
            f"<td>{escape(str(run['status']))}</td>"
            f"<td>{escape(annotated)}</td>"
            f"<td>{escape(str(run['started_at']))}</td>"
            f"<td>{escape(str(run['error'] or ''))}</td>"
            "</tr>"
        )
    return "<table><thead><tr><th>ID</th><th>状态</th><th>邮件数</th><th>开始时间</th><th>错误</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def _check_html(check) -> str:
    return (
        f"<div class=\"check-row {escape(check.status)}\">"
        f"<strong>{escape(check.name)}</strong>"
        f"<span>{escape(check.detail)}</span>"
        f"{f'<small>{escape(check.action)}</small>' if check.action else ''}"
        "</div>"
    )


def _action_form(action: str, label: str, danger: bool = False) -> str:
    klass = "danger" if danger else ""
    return f"<form method=\"post\" action=\"{escape(action)}\"><button class=\"{klass}\" type=\"submit\">{escape(label)}</button></form>"


def _dry_run_form() -> str:
    return (
        "<form class=\"inline\" method=\"post\" action=\"/action/dry-run\">"
        "<input name=\"limit\" type=\"number\" min=\"1\" max=\"200\" value=\"10\">"
        "<button type=\"submit\">试跑并生成预览</button></form>"
    )


def _message_from_query(query: str) -> tuple[str, str] | None:
    parsed = parse_qs(query)
    message = parsed.get("message", [""])[0]
    if not message:
        return None
    return parsed.get("level", ["ok"])[0], message


def _message_html(message: tuple[str, str] | None) -> str:
    if not message:
        return ""
    level, text = message
    return f"<div class=\"message {escape(level)}\">{escape(text)}</div>"


def _fresh_settings():
    return settings_from_values(read_env_values())


def _render_sample_via_cli() -> None:
    render_sample_digest(_fresh_settings())


def _capture_output(callback) -> str:
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        callback()
    return stream.getvalue()


def _run_silently(callback):
    stream = io.StringIO()
    with contextlib.redirect_stdout(stream):
        return callback()


def _digest_summary(digest) -> str:
    if digest is None:
        return ""
    total = len(digest.records)
    if total == 0:
        return "当前窗口没有新邮件。"
    p0 = digest.priority_counts.get("P0", 0)
    p1 = digest.priority_counts.get("P1", 0)
    threaded = sum(1 for count in digest.thread_counts.values() if count > 1)
    extra = f"，{threaded} 个会话有多封新回复" if threaded else ""
    return f"处理 {total} 封新邮件，P0 {p0} 封、P1 {p1} 封{extra}。"


def _auth_summary(checks) -> str:
    if not checks:
        return "未执行登录测试。"
    parts = []
    for check in checks:
        marker = "✓" if check.status == "ok" else "×"
        parts.append(f"{marker} {check.name}：{check.detail}")
    return " | ".join(parts)


def _short_output(output: str) -> str:
    compact = " ".join(output.split())
    return compact[:160]


def _optional_int(value: str | None, default: int) -> int:
    try:
        return int(value or default)
    except ValueError:
        return default


_CSS = """
:root{color-scheme:light;--bg:#f5f7fb;--panel:#fff;--text:#172033;--muted:#617086;--line:#dfe6ef;--ok:#0f7b45;--warn:#996c00;--fail:#b3261e;--brand:#2754c5}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:Arial,'Microsoft YaHei',sans-serif}
.shell{max-width:1120px;margin:0 auto;padding:28px}
.top{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:20px}
h1{margin:0;font-size:28px;line-height:36px} h2{margin:0 0 14px;font-size:18px} p{margin:6px 0;color:var(--muted)}
.link{display:inline-block;padding:9px 12px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--brand);text-decoration:none}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;margin-bottom:16px}
.checks{display:grid;gap:8px}.check-row{border:1px solid var(--line);border-left-width:5px;border-radius:6px;padding:10px}.check-row strong{display:block}.check-row span{display:block;margin-top:3px;color:var(--muted)}.check-row small{display:block;margin-top:4px;color:var(--muted)}
.check-row.ok{border-left-color:var(--ok)}.check-row.warn{border-left-color:var(--warn)}.check-row.fail{border-left-color:var(--fail)}
.actions{display:grid;gap:10px}.actions form{margin:0}.inline{display:flex;gap:8px}.inline input{width:84px}
button{border:0;border-radius:6px;background:var(--brand);color:#fff;padding:10px 13px;font-weight:700;cursor:pointer}button.danger{background:#9f1d1d}
.config button{margin-top:14px}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.form-grid label span{display:block;margin-bottom:5px;color:var(--muted);font-size:13px}
input{width:100%;border:1px solid var(--line);border-radius:6px;padding:9px;background:#fff;color:var(--text)}
.bool-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;margin-top:14px}.check{color:var(--muted);font-size:14px}.check input{width:auto}
table{width:100%;border-collapse:collapse}th,td{padding:9px;border-bottom:1px solid var(--line);text-align:left;font-size:14px}th{color:var(--muted)}.muted{color:var(--muted)}
.message{border-radius:6px;padding:12px;margin-bottom:16px;background:#e9f7ef;color:#0f5f37}.message.error{background:#fdeaea;color:#9f1d1d}
@media(max-width:760px){.grid,.form-grid,.bool-grid{grid-template-columns:1fr}.top{display:block}.shell{padding:16px}}
"""
