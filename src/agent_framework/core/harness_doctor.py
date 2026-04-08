from __future__ import annotations

import argparse
import json
from typing import Any

from agent_framework.core.harness_health import build_liveness_report, build_readiness_report
from agent_framework.core.system_status import collect_system_status


def build_doctor_report(app) -> dict[str, Any]:
    readiness = build_readiness_report(app)
    return {
        "service": "agent-framework",
        "liveness": build_liveness_report(),
        "readiness": readiness,
        "system_status": collect_system_status(app),
    }


def render_text_report(report: dict[str, Any]) -> str:
    readiness = report["readiness"]
    lines = [
        "Agent Framework Doctor",
        f"liveness  : {report['liveness']['status']}",
        f"readiness : {readiness['status']}",
        f"summary   : pass={readiness['summary']['pass']} warn={readiness['summary']['warn']} fail={readiness['summary']['fail']}",
        "checks:",
    ]
    for check in readiness["checks"]:
        lines.append(f"  - {check['name']}: {check['status']} | {check['summary']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent Framework doctor")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    from agent_framework.web.web_ui import app

    report = build_doctor_report(app)
    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(report))
    return 0 if report["readiness"]["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
