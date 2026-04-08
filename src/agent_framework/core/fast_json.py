"""
快速 JSON 优化 - 使用 orjson/ujson 替代标准 json
无需 Rust 编译，pip install 即可使用
"""

import sys

# 尝试导入高性能 JSON 库
_json_impl = None

try:
    import orjson
    _json_impl = 'orjson'
    print(f"[FastJSON] 使用 orjson (最快，Rust 实现)", file=sys.stderr)
except ImportError:
    try:
        import ujson
        _json_impl = 'ujson'
        print(f"[FastJSON] 使用 ujson (快速，C 实现)", file=sys.stderr)
    except ImportError:
        import json as _json
        _json_impl = 'json'
        print(f"[FastJSON] 使用标准 json (回退)", file=sys.stderr)


def loads(s, **kwargs):
    """
    解析 JSON 字符串

    性能对比:
    - orjson: 2-3x faster than json
    - ujson: 1.5-2x faster than json
    """
    if _json_impl == 'orjson':
        # orjson 只接受 bytes 或 str
        if isinstance(s, bytes):
            return orjson.loads(s)
        return orjson.loads(s.encode('utf-8'))
    elif _json_impl == 'ujson':
        return ujson.loads(s, **kwargs)
    else:
        return _json.loads(s, **kwargs)


def dumps(obj, **kwargs):
    """
    序列化为 JSON 字符串

    性能对比:
    - orjson: 2-3x faster than json
    - ujson: 1.5-2x faster than json
    """
    if _json_impl == 'orjson':
        # orjson 返回 bytes，需要解码
        result = orjson.dumps(obj)
        return result.decode('utf-8')
    elif _json_impl == 'ujson':
        return ujson.dumps(obj, **kwargs)
    else:
        return _json.dumps(obj, **kwargs)


def load(fp, **kwargs):
    """从文件加载 JSON"""
    return loads(fp.read(), **kwargs)


def dump(obj, fp, **kwargs):
    """保存 JSON 到文件"""
    fp.write(dumps(obj, **kwargs))


# 兼容标准库接口
JSONDecodeError = Exception if _json_impl == 'orjson' else (
    ujson.JSONDecodeError if _json_impl == 'ujson' else _json.JSONDecodeError
)


def get_implementation():
    """获取当前使用的 JSON 实现"""
    return _json_impl


def benchmark():
    """性能测试"""
    import time
    import json as std_json

    # 测试数据
    test_data = {
        'users': [
            {
                'id': i,
                'name': f'User {i}',
                'email': f'user{i}@example.com',
                'metadata': {
                    'created_at': '2024-01-01',
                    'tags': ['tag1', 'tag2', 'tag3'],
                    'scores': [1.0, 2.0, 3.0, 4.0, 5.0]
                }
            }
            for i in range(1000)
        ]
    }

    # 标准 json
    start = time.time()
    for _ in range(100):
        json_str = std_json.dumps(test_data)
        _ = std_json.loads(json_str)
    std_time = time.time() - start

    # fast_json
    start = time.time()
    for _ in range(100):
        json_str = dumps(test_data)
        _ = loads(json_str)
    fast_time = time.time() - start

    speedup = std_time / fast_time

    print(f"\n性能测试结果:")
    print(f"  标准 json: {std_time:.4f} 秒")
    print(f"  fast_json ({_json_impl}): {fast_time:.4f} 秒")
    print(f"  性能提升: {speedup:.2f}x")

    return speedup


if __name__ == "__main__":
    print(f"当前 JSON 实现: {_json_impl}")
    print(f"\n安装建议:")
    print(f"  pip install orjson  # 推荐，最快（Rust 实现）")
    print(f"  pip install ujson   # 备选，快速（C 实现）")

    # 运行性能测试
    benchmark()
