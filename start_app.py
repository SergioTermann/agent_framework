from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def add_src_to_path(repo_root: Path) -> None:
    src_path = repo_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))


def load_server_config(repo_root: Path) -> tuple[str, int]:
    add_src_to_path(repo_root)

    try:
        from agent_framework.core.config import get_config

        cfg = get_config()
        return cfg.server.host, cfg.server.port
    except Exception:
        host = os.environ.get("HOST", "0.0.0.0")
        port = int(os.environ.get("PORT", "5000"))
        return host, port


def build_runtime_env(repo_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(repo_root / "src")
    existing_pythonpath = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing_pythonpath else f"{src_path}{os.pathsep}{existing_pythonpath}"
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def wait_until_ready(url: str, process: subprocess.Popen[bytes], timeout: float) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            pass
        time.sleep(1)
    return False


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def ensure_env_file(repo_root: Path) -> None:
    env_file = repo_root / ".env"
    env_example = repo_root / ".env.example"
    if env_file.exists() or not env_example.exists():
        return
    env_file.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
    print("[info] created .env from .env.example")


def build_legacy_gateway(repo_root: Path) -> Path | None:
    gateway_bin = repo_root / "go_services" / "gateway" / "gateway"
    if sys.platform == "win32":
        gateway_bin = gateway_bin.with_suffix(".exe")
    if gateway_bin.exists():
        return gateway_bin

    print("[info] building legacy go gateway ...")
    build_result = subprocess.run(
        ["go", "build", "-o", str(gateway_bin), "./cmd/gateway"],
        cwd=repo_root / "go_services" / "gateway",
        env={**os.environ, "CGO_ENABLED": "0"},
    )
    if build_result.returncode != 0:
        return None
    return gateway_bin


def build_gateway_control_plane(repo_root: Path) -> Path | None:
    gateway_bin = repo_root / "services" / "gateway-go" / "gateway-go"
    if sys.platform == "win32":
        gateway_bin = gateway_bin.with_suffix(".exe")
    if gateway_bin.exists():
        return gateway_bin

    print("[info] building gateway-go control plane ...")
    build_result = subprocess.run(
        ["go", "build", "-o", str(gateway_bin), "./cmd/gateway"],
        cwd=repo_root / "services" / "gateway-go",
        env={**os.environ, "CGO_ENABLED": "0"},
    )
    if build_result.returncode != 0:
        return None
    return gateway_bin


def main() -> int:
    parser = argparse.ArgumentParser(description="Agent Framework launcher")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser after startup")
    parser.add_argument("--timeout", type=float, default=60, help="Startup timeout in seconds")
    parser.add_argument("--smoke-test", action="store_true", help="Exit after readiness checks pass")
    parser.add_argument(
        "--with-gateway",
        action="store_true",
        help="Start the legacy Go edge gateway on the public port and Flask on :5001",
    )
    parser.add_argument(
        "--with-go-control-plane",
        action="store_true",
        help="Start services/gateway-go as a sidecar and proxy /api/gateway/* from Flask to Go",
    )
    args = parser.parse_args()

    if args.with_gateway and args.with_go_control_plane:
        print("[error] --with-gateway and --with-go-control-plane cannot be used together")
        return 2

    repo_root = Path(__file__).resolve().parent
    ensure_env_file(repo_root)

    host, port = load_server_config(repo_root)
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    app_url = f"http://{browser_host}:{port}"

    process: subprocess.Popen[bytes] | None = None
    gateway_process: subprocess.Popen[bytes] | None = None
    go_control_plane_process: subprocess.Popen[bytes] | None = None

    try:
        if args.with_gateway:
            flask_port = 5001
            flask_url = f"http://{browser_host}:{flask_port}"
            go_control_plane_port = int(os.environ.get("GATEWAY_CONTROL_PLANE_PORT", "7000"))
            go_control_plane_url = f"http://127.0.0.1:{go_control_plane_port}"

            print("=" * 72)
            print("Agent Framework startup (legacy gateway mode)")
            print(f"repo        : {repo_root}")
            print(f"python      : {sys.executable}")
            print(f"flask       : {flask_url}")
            print(f"go gateway  : {app_url}")
            print("=" * 72)

            flask_env = build_runtime_env(repo_root)
            flask_env["INTERNAL_PORT"] = str(flask_port)
            process = subprocess.Popen(
                [sys.executable, "-m", "agent_framework.web.web_ui"],
                cwd=repo_root,
                env=flask_env,
            )

            if not wait_until_ready(flask_url, process, args.timeout):
                code = process.poll()
                if code is None:
                    print(f"[error] Flask backend did not become ready within {args.timeout:.0f}s")
                    stop_process(process)
                    return 1
                print(f"[error] Flask backend exited with code {code}")
                return code

            control_plane_bin = build_gateway_control_plane(repo_root)
            if control_plane_bin is None:
                print("[error] failed to build gateway-go")
                stop_process(process)
                return 1

            control_plane_env = os.environ.copy()
            control_plane_env["GATEWAY_GO_LISTEN"] = f":{go_control_plane_port}"
            control_plane_env["FRONTEND_STATIC_DIR"] = str(repo_root / "frontend" / "static")
            if "APP_AUTH_SECRET" not in control_plane_env and "JWT_SECRET_KEY" in control_plane_env:
                control_plane_env["APP_AUTH_SECRET"] = control_plane_env["JWT_SECRET_KEY"]
            control_plane_env.setdefault("GATEWAY_REQUIRE_AUTH", "true")

            go_control_plane_process = subprocess.Popen(
                [str(control_plane_bin)],
                cwd=repo_root,
                env=control_plane_env,
            )
            if not wait_until_ready(f"{go_control_plane_url}/health", go_control_plane_process, 15):
                print("[error] gateway-go control plane failed to start")
                stop_process(go_control_plane_process)
                stop_process(process)
                return 1

            gateway_bin = build_legacy_gateway(repo_root)
            if gateway_bin is None:
                print("[error] failed to build legacy go gateway")
                stop_process(go_control_plane_process)
                stop_process(process)
                return 1

            gw_env = os.environ.copy()
            gw_env["GATEWAY_LISTEN"] = f":{port}"
            gw_env["PYTHON_BACKEND_URL"] = f"http://127.0.0.1:{flask_port}"
            gw_env["GATEWAY_CONTROL_PLANE_URL"] = go_control_plane_url
            gw_env["STATIC_DIR"] = str(repo_root / "src" / "agent_framework" / "static")
            gateway_process = subprocess.Popen([str(gateway_bin)], cwd=repo_root, env=gw_env)

            if not wait_until_ready(f"{app_url}/health", gateway_process, 15):
                print("[error] legacy go gateway failed to start")
                stop_process(gateway_process)
                stop_process(go_control_plane_process)
                stop_process(process)
                return 1
        else:
            runtime_env = build_runtime_env(repo_root)
            if args.with_go_control_plane:
                go_control_plane_port = int(os.environ.get("GATEWAY_CONTROL_PLANE_PORT", "7000"))
                go_control_plane_url = f"http://127.0.0.1:{go_control_plane_port}"
                runtime_env["GATEWAY_CONTROL_PLANE"] = "go"
                runtime_env["GATEWAY_CONTROL_PLANE_URL"] = go_control_plane_url
            else:
                go_control_plane_url = ""

            print("=" * 72)
            print("Agent Framework startup")
            print(f"repo        : {repo_root}")
            print(f"python      : {sys.executable}")
            print(f"app         : {app_url}")
            if go_control_plane_url:
                print(f"go control  : {go_control_plane_url}")
            print("=" * 72)

            if args.with_go_control_plane:
                gateway_bin = build_gateway_control_plane(repo_root)
                if gateway_bin is None:
                    print("[error] failed to build gateway-go")
                    return 1

                gw_env = os.environ.copy()
                gw_env["GATEWAY_GO_LISTEN"] = f":{go_control_plane_port}"
                gw_env["FRONTEND_STATIC_DIR"] = str(repo_root / "frontend" / "static")
                if "APP_AUTH_SECRET" not in gw_env and "JWT_SECRET_KEY" in gw_env:
                    gw_env["APP_AUTH_SECRET"] = gw_env["JWT_SECRET_KEY"]
                gw_env.setdefault("GATEWAY_REQUIRE_AUTH", "true")

                go_control_plane_process = subprocess.Popen(
                    [str(gateway_bin)],
                    cwd=repo_root,
                    env=gw_env,
                )
                if not wait_until_ready(f"{go_control_plane_url}/health", go_control_plane_process, 15):
                    print("[error] gateway-go control plane failed to start")
                    stop_process(go_control_plane_process)
                    return 1

            process = subprocess.Popen(
                [sys.executable, "-m", "agent_framework.web.web_ui"],
                cwd=repo_root,
                env=runtime_env,
            )

            if not wait_until_ready(app_url, process, args.timeout):
                code = process.poll()
                if code is None:
                    print(f"[error] app did not become ready within {args.timeout:.0f}s")
                    if go_control_plane_process:
                        stop_process(go_control_plane_process)
                    stop_process(process)
                    return 1
                print(f"[error] app exited with code {code}")
                return code

        if args.smoke_test:
            if go_control_plane_process:
                stop_process(go_control_plane_process)
            if gateway_process:
                stop_process(gateway_process)
            stop_process(process)
            print("[ok] smoke test passed")
            return 0

        if not args.no_browser:
            try:
                webbrowser.open(app_url)
            except Exception as exc:
                print(f"[info] browser auto-open failed, visit {app_url} manually ({exc})")

        print("[info] press Ctrl+C to stop")
        return process.wait()
    except KeyboardInterrupt:
        print("\n[info] stopping services ...")
        if go_control_plane_process:
            stop_process(go_control_plane_process)
        if gateway_process:
            stop_process(gateway_process)
        stop_process(process)
        return 0
    finally:
        if go_control_plane_process and go_control_plane_process.poll() is None:
            stop_process(go_control_plane_process)
        if gateway_process and gateway_process.poll() is None:
            stop_process(gateway_process)
        if process and process.poll() is None:
            stop_process(process)


if __name__ == "__main__":
    raise SystemExit(main())
