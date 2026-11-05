"""Collect reproducible suite metrics into reports/metrics.json and metrics.md."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"


def _collect_nodeids(marker: str | None = None) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        "-q",
        "--override-ini",
        "addopts=",
    ]
    if marker:
        command.extend(["-m", marker])
    result = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    nodeids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith("="):
            nodeids.append(line)
    return nodeids


def _endpoint(nodeid: str) -> str:
    path, _, rest = nodeid.partition("::")
    module = Path(path).stem
    name = rest.split("::")[-1].lower()
    if module == "test_framework":
        return "framework"
    if module == "test_auth":
        if "login" in name:
            return "auth/login"
        if "logout" in name:
            return "auth/logout"
        return "auth/me"
    if module == "test_books_query":
        if "get_book" in name:
            return "books/get"
        if "unknown_route" in name:
            return "cross-cutting/contract"
        return "books/list"
    if module == "test_books_write":
        if "create" in name:
            return "books/create"
        if "update" in name:
            return "books/update"
        return "books/delete"
    if module == "test_borrow":
        if "TestBorrowList" in rest:
            return "borrows/list"
        if "return" in name:
            return "borrows/return"
        return "borrows/borrow"
    if module == "test_contract":
        if "stats" in name:
            return "stats/overview"
        return "cross-cutting/contract"
    return "uncategorized"


def _runtime_seconds() -> float | None:
    path = REPORTS / "junit.xml"
    if not path.exists():
        return None
    try:
        root = ET.parse(path).getroot()
        suite = root.find("testsuite") if root.tag == "testsuites" else root
        return float(suite.attrib.get("time", "0"))
    except (ET.ParseError, ValueError):
        return None


def main() -> None:
    all_ids = _collect_nodeids()
    negative = set(_collect_nodeids("negative"))
    smoke = set(_collect_nodeids("smoke"))
    db_marked = set(_collect_nodeids("db"))
    framework = {node for node in all_ids if node.startswith("tests/test_framework.py")}
    business = [node for node in all_ids if node not in framework]
    endpoints = Counter(_endpoint(node) for node in business)
    modules = Counter(node.split("::")[0] for node in all_ids)
    meta_path = REPORTS / "run_meta.json"
    run_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    metrics = {
        "total_collected": len(all_ids),
        "business_cases": len(business),
        "framework_self_checks": len(framework),
        "negative_cases": len([node for node in business if node in negative]),
        "smoke_cases": len([node for node in business if node in smoke]),
        "db_assertion_cases": len([node for node in business if node in db_marked]),
        "interfaces": 12,
        "by_endpoint": dict(sorted(endpoints.items())),
        "by_module": dict(sorted(modules.items())),
        "last_run": run_meta,
        "pytest_reported_seconds": _runtime_seconds(),
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "# 接口自动化测试量化结果",
        "",
        "> 由 `python scripts/collect_metrics.py` 从 pytest 收集结果与 junit.xml 自动生成。",
        "",
        f"- 业务接口数：**{metrics['interfaces']}**",
        f"- 接口用例数：**{metrics['business_cases']}**",
        f"- 框架自检：{metrics['framework_self_checks']} 条（不计入接口用例）",
        f"- 逆向/异常用例：**{metrics['negative_cases']}** 条",
        f"- 冒烟用例：{metrics['smoke_cases']} 条",
        f"- 含数据库断言用例：{metrics['db_assertion_cases']} 条",
        f"- pytest 测试耗时：{metrics['pytest_reported_seconds'] or 0:.2f} 秒",
        f"- 回归命令总耗时：{run_meta.get('elapsed_seconds', '未记录')} 秒",
        "",
        "## 按接口分布",
        "",
        "| 接口分组 | 用例数 |",
        "|---|---:|",
    ]
    for endpoint, count in sorted(endpoints.items()):
        lines.append(f"| {endpoint} | {count} |")
    lines.extend(["", "## 按测试模块分布", "", "| 模块 | 用例数 |", "|---|---:|"])
    for module, count in sorted(modules.items()):
        lines.append(f"| {module} | {count} |")
    lines.append("")
    (REPORTS / "metrics.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
