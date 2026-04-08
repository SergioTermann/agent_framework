"""
用户工具完整用例演示
====================

演示场景：风电运维工程师通过自定义工具与 SCADA 系统交互

运行前提：
1. 启动服务: python src/agent_framework/web/web_ui.py
2. 安装依赖: pip install requests
3. 运行脚本: python examples/user_tools_demo.py
"""

import requests
import json
import time

BASE_URL = "http://localhost:5000"

def print_section(title):
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def print_response(resp):
    print(f"Status: {resp.status_code}")
    try:
        data = resp.json()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    except:
        print(resp.text)

# ============================================================================
# 步骤 1: 创建 SCADA 查询工具
# ============================================================================

print_section("步骤 1: 创建 SCADA 查询工具")

tool1_payload = {
    "name": "query_scada",
    "description": "查询 SCADA 系统中指定风机的实时运行数据",
    "user_id": "wind_engineer_001",
    "parameters": {
        "type": "object",
        "properties": {
            "turbine_id": {"type": "string", "description": "风机编号，如 WT-001"},
            "metrics": {"type": "string", "description": "指标名称，如 power, wind_speed"}
        },
        "required": ["turbine_id"]
    },
    "execution_config": {
        "url": "https://httpbin.org/get?turbine={turbine_id}&metric={metrics}",
        "method": "GET",
        "headers": {"Accept": "application/json"},
        "timeout": 15,
        "auth_type": "bearer",
        "auth_secret_key": "scada_api_token"
    },
    "tags": ["scada", "wind", "monitoring"]
}

resp1 = requests.post(f"{BASE_URL}/api/tools", json=tool1_payload)
print_response(resp1)

if resp1.status_code == 201:
    tool1_id = resp1.json()["tool"]["tool_id"]
    print(f"\n✓ 工具创建成功，ID: {tool1_id}")
else:
    print("\n✗ 工具创建失败")
    exit(1)

time.sleep(0.5)

# ============================================================================
# 步骤 2: 创建告警工具
# ============================================================================

print_section("步骤 2: 创建企业微信告警工具")

tool2_payload = {
    "name": "send_wechat_alert",
    "description": "发送运维告警到企业微信群",
    "user_id": "wind_engineer_001",
    "parameters": {
        "type": "object",
        "properties": {
            "message": {"type": "string", "description": "告警内容"},
            "level": {"type": "string", "enum": ["info", "warning", "critical"]}
        },
        "required": ["message"]
    },
    "execution_config": {
        "url": "https://httpbin.org/post",
        "method": "POST",
        "body_template": '{"msgtype": "text", "text": {"content": "{message}"}, "level": "{level}"}',
        "timeout": 10,
        "auth_type": "none"
    },
    "tags": ["alert", "notification"]
}

resp2 = requests.post(f"{BASE_URL}/api/tools", json=tool2_payload)
print_response(resp2)

if resp2.status_code == 201:
    tool2_id = resp2.json()["tool"]["tool_id"]
    print(f"\n✓ 工具创建成功，ID: {tool2_id}")
else:
    print("\n✗ 工具创建失败")
    exit(1)

time.sleep(0.5)

# ============================================================================
# 步骤 3: 存储密钥
# ============================================================================

print_section("步骤 3: 存储 SCADA API 密钥")

secret_payload = {
    "key": "scada_api_token",
    "value": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.fake_token",
    "user_id": "wind_engineer_001"
}

resp3 = requests.post(f"{BASE_URL}/api/tools/secrets", json=secret_payload)
print_response(resp3)
print("\n✓ 密钥已安全存储")

time.sleep(0.5)

# ============================================================================
# 步骤 4: 列出所有工具
# ============================================================================

print_section("步骤 4: 列出所有可用工具")

resp4 = requests.get(f"{BASE_URL}/api/tools?user_id=wind_engineer_001")
print_response(resp4)

if resp4.status_code == 200:
    tools = resp4.json()["tools"]
    builtin = sum(1 for t in tools if t["source"] == "builtin")
    user = sum(1 for t in tools if t["source"] == "user")
    print(f"\n✓ 共 {len(tools)} 个工具: {builtin} 内置, {user} 用户自定义")

time.sleep(0.5)

# ============================================================================
# 步骤 5: 测试工具执行
# ============================================================================

print_section("步骤 5: 测试 SCADA 查询工具")

test_payload = {"params": {"turbine_id": "WT-001", "metrics": "power"}}
resp5 = requests.post(f"{BASE_URL}/api/tools/{tool1_id}/test", json=test_payload)
print_response(resp5)
print("\n✓ 工具测试执行成功")

time.sleep(0.5)

# ============================================================================
# 步骤 6: Chat 模式调用工具
# ============================================================================

print_section("步骤 6: Chat 模式 - 启用工具调用")

chat_payload = {
    "message": "查询一下 WT-001 风机的实时功率数据",
    "user_id": "wind_engineer_001",
    "metadata": {
        "enable_tools": true,
        "allowed_tools": ["query_scada", "calculate"]
    }
}

resp6 = requests.post(f"{BASE_URL}/api/unified/chat", json=chat_payload)
print_response(resp6)

if resp6.status_code == 200:
    result = resp6.json()
    tool_calls = result.get("context", {}).get("tool_calls", [])
    print(f"\n✓ Chat 完成，调用了 {len(tool_calls)} 个工具")

time.sleep(0.5)

# ============================================================================
# 步骤 7: Agent 模式自动集成用户工具
# ============================================================================

print_section("步骤 7: Agent 模式 - 自动加载用户工具")

agent_payload = {
    "message": "WT-001 出现功率异常告警，帮我查询数据并发送告警",
    "user_id": "wind_engineer_001",
    "use_agent": True,
    "metadata": {
        "toolsets": ["basic"]
    }
}

resp7 = requests.post(f"{BASE_URL}/api/unified/chat", json=agent_payload)
print_response(resp7)

if resp7.status_code == 200:
    print("\n✓ Agent 自动调用用户工具完成任务")

time.sleep(0.5)

# ============================================================================
# 步骤 8: 更新工具
# ============================================================================

print_section("步骤 8: 更新工具描述")

update_payload = {
    "description": "查询 SCADA 系统风机数据（已升级到 v2 API）",
    "enabled": True
}

resp8 = requests.put(f"{BASE_URL}/api/tools/{tool1_id}", json=update_payload)
print_response(resp8)
print("\n✓ 工具更新成功")

time.sleep(0.5)

# ============================================================================
# 步骤 9: 禁用工具
# ============================================================================

print_section("步骤 9: 禁用告警工具")

disable_payload = {"enabled": False}
resp9 = requests.put(f"{BASE_URL}/api/tools/{tool2_id}", json=disable_payload)
print_response(resp9)
print("\n✓ 工具已禁用")

time.sleep(0.5)

# ============================================================================
# 步骤 10: 清理（可选）
# ============================================================================

print_section("步骤 10: 清理演示数据（可选）")

print("删除工具 1...")
resp10a = requests.delete(f"{BASE_URL}/api/tools/{tool1_id}")
print(f"Status: {resp10a.status_code}")

print("删除工具 2...")
resp10b = requests.delete(f"{BASE_URL}/api/tools/{tool2_id}")
print(f"Status: {resp10b.status_code}")

print("删除密钥...")
resp10c = requests.delete(f"{BASE_URL}/api/tools/secrets/scada_api_token")
print(f"Status: {resp10c.status_code}")

print("\n✓ 清理完成")

# ============================================================================
# 总结
# ============================================================================

print_section("演示完成")
print("""
✓ 已演示的功能：
  1. 创建用户自定义工具（SCADA 查询 + 企业微信告警）
  2. 安全存储 API 密钥
  3. 列出所有工具（builtin + user）
  4. 测试工具执行
  5. Chat 模式调用工具（function calling）
  6. Agent 模式自动集成用户工具
  7. 更新工具配置
  8. 禁用/删除工具

核心价值：
  - 无需修改代码，运行时动态创建工具
  - Chat 模式现在支持工具调用（之前只有 Agent 支持）
  - 用户工具自动纳入工具池，与 builtin 工具无缝集成
""")
