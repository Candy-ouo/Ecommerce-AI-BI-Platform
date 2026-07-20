"""7 接口冒烟测试：启动 Flask → 逐接口验证 → 输出结果"""
import subprocess, time, requests, sys

BASE = "http://localhost:5000"

print("启动 Flask ...")
proc = subprocess.Popen(
    ["python", "app.py"],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    cwd="backend",
)
time.sleep(4)

passed = 0
failed = 0

tests = [
    ("GET", "/api/kpi/cards", None, ["cards"]),
    ("GET", "/api/trend/active", None, ["dates"]),
    ("GET", "/api/top/items?limit=3&sort_by=pv", None, ["items"]),
    ("GET", "/api/funnel", None, ["stages"]),
    ("GET", "/api/rfm/dist", None, ["labels"]),
    ("GET", "/api/recommend?user_id=123", None, ["items"]),
]

print("=== 7 接口冒烟测试 ===\n")
for method, path, body, expected_keys in tests:
    try:
        if method == "GET":
            r = requests.get(f"{BASE}{path}", timeout=5)
        else:
            r = requests.post(f"{BASE}{path}", json=body, timeout=5)
        data = r.json()
        ok = all(k in data for k in expected_keys)
        if r.status_code == 200 and ok:
            passed += 1
            print(f"\033[92m[PASS]\033[0m {method} {path} → {r.status_code} | keys={list(data.keys())}")
        else:
            failed += 1
            print(f"\033[91m[FAIL]\033[0m {method} {path} → {r.status_code} | keys={list(data.keys())} | missing={[k for k in expected_keys if k not in data]}")
    except Exception as e:
        failed += 1
        print(f"\033[91m[FAIL]\033[0m {method} {path} → Exception: {e}")

# chat (SSE)
try:
    r = requests.post(f"{BASE}/api/chat", json={"message": "测试"}, stream=True, timeout=5)
    first = next(r.iter_lines())
    if first:
        decoded = first.decode() if isinstance(first, bytes) else first
        if "type" in decoded:
            passed += 1
            print(f"\033[92m[PASS]\033[0m POST /api/chat → SSE 流式正常")
        else:
            failed += 1
            print(f"\033[91m[FAIL]\033[0m POST /api/chat → SSE 格式异常")
    else:
        failed += 1
        print(f"\033[91m[FAIL]\033[0m POST /api/chat → 无响应")
except Exception as e:
    failed += 1
    print(f"\033[91m[FAIL]\033[0m POST /api/chat → Exception: {e}")

proc.terminate()

total = passed + failed
print(f"\n=== 结果: {passed}/{total} 通过 | {failed}/{total} 失败 ===")
sys.exit(0 if failed == 0 else 1)
