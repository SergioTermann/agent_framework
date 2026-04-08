#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试 data_platform 整合是否成功
"""
import sys
import io
from pathlib import Path

# 设置标准输出编码为 UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_static_files():
    """测试静态文件是否存在"""
    static_dir = Path("src/agent_framework/static/data_platform")

    print("检查静态文件...")
    required_files = [
        "index.html",
        "js",
        "assets",
        "images",
        "models",
        "textures",
    ]

    for item in required_files:
        path = static_dir / item
        if path.exists():
            print(f"[OK] {item} 存在")
        else:
            print(f"[FAIL] {item} 不存在")
            return False

    return True

def test_routes():
    """测试路由是否正确配置"""
    print("\n检查路由配置...")

    try:
        from agent_framework.web.web_ui import app

        routes = []
        for rule in app.url_map.iter_rules():
            if 'data-platform' in rule.rule:
                routes.append(rule.rule)
                print(f"[OK] 路由: {rule.rule} -> {rule.endpoint}")

        if len(routes) >= 2:
            print(f"\n找到 {len(routes)} 个 data-platform 路由")
            return True
        else:
            print("\n[FAIL] data-platform 路由配置不完整")
            return False

    except Exception as e:
        print(f"[FAIL] 加载路由失败: {e}")
        return False

def test_portal_integration():
    """测试门户页面集成"""
    print("\n检查门户页面集成...")

    portal_file = Path("src/agent_framework/templates/portal.html")
    if not portal_file.exists():
        print("[FAIL] portal.html 不存在")
        return False

    content = portal_file.read_text(encoding='utf-8')
    if '/data-platform' in content and 'Data Platform' in content:
        print("[OK] portal.html 已包含 Data Platform 入口")
        return True
    else:
        print("[FAIL] portal.html 未包含 Data Platform 入口")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Data Platform 整合测试")
    print("=" * 60)

    results = []

    results.append(("静态文件", test_static_files()))
    results.append(("路由配置", test_routes()))
    results.append(("门户集成", test_portal_integration()))

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{name}: {status}")

    all_passed = all(r[1] for r in results)

    if all_passed:
        print("\n[SUCCESS] 所有测试通过！")
        print("\n访问方式:")
        print("  1. 直接访问: http://localhost:5000/data-platform")
        print("  2. 门户入口: http://localhost:5000/portal")
        print("\n提示: 需要先启动 Flask 服务器")
    else:
        print("\n[ERROR] 部分测试失败，请检查配置")
        sys.exit(1)
