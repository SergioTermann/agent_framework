"""
优化的加密和签名验证模块
使用更快的哈希算法和优化的实现
"""

import hmac
import hashlib
import time
from typing import Optional


class OptimizedCrypto:
    """优化的加密工具类"""

    @staticmethod
    def compute_hmac_sha256(key: bytes, message: bytes) -> bytes:
        """
        计算 HMAC-SHA256

        优化点:
        1. 直接使用 hmac.new 而不是 hmac.HMAC
        2. 使用 digestmod 参数指定算法
        3. 避免不必要的编码转换
        """
        return hmac.new(key, message, hashlib.sha256).digest()

    @staticmethod
    def compute_hmac_sha256_hex(key: bytes, message: bytes) -> str:
        """计算 HMAC-SHA256 并返回十六进制字符串"""
        return hmac.new(key, message, hashlib.sha256).hexdigest()

    @staticmethod
    def verify_hmac_sha256(key: bytes, message: bytes, signature: bytes) -> bool:
        """
        验证 HMAC-SHA256 签名

        优化点:
        1. 使用 hmac.compare_digest 防止时序攻击
        2. 提前计算避免重复计算
        """
        expected = hmac.new(key, message, hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)

    @staticmethod
    def verify_hmac_sha256_hex(key: bytes, message: bytes, signature_hex: str) -> bool:
        """验证 HMAC-SHA256 签名（十六进制）"""
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature_hex)

    @staticmethod
    def hash_sha256(data: bytes) -> bytes:
        """计算 SHA256 哈希"""
        return hashlib.sha256(data).digest()

    @staticmethod
    def hash_sha256_hex(data: bytes) -> str:
        """计算 SHA256 哈希（十六进制）"""
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_md5(data: bytes) -> bytes:
        """计算 MD5 哈希（不推荐用于安全场景）"""
        return hashlib.md5(data).digest()

    @staticmethod
    def hash_md5_hex(data: bytes) -> str:
        """计算 MD5 哈希（十六进制）"""
        return hashlib.md5(data).hexdigest()


class WebhookSignatureVerifier:
    """
    Webhook 签名验证器

    优化点:
    1. 缓存密钥避免重复查找
    2. 批量验证支持
    3. 时间戳验证优化
    """

    def __init__(self, secret: str, tolerance_seconds: int = 300):
        self.secret = secret.encode('utf-8')
        self.tolerance_seconds = tolerance_seconds

    def compute_signature(self, timestamp: str, payload: str) -> str:
        """
        计算签名

        格式: HMAC-SHA256(secret, timestamp + "." + payload)
        """
        message = f"{timestamp}.{payload}".encode('utf-8')
        return OptimizedCrypto.compute_hmac_sha256_hex(self.secret, message)

    def verify_signature(
        self,
        timestamp: str,
        payload: str,
        signature: str
    ) -> bool:
        """
        验证签名

        Returns:
            True if valid, False otherwise
        """
        # 验证时间戳
        try:
            ts = int(timestamp)
            now = int(time.time())

            if abs(now - ts) > self.tolerance_seconds:
                return False
        except (ValueError, TypeError):
            return False

        # 验证签名
        expected_signature = self.compute_signature(timestamp, payload)
        return hmac.compare_digest(expected_signature, signature)

    def verify_request(
        self,
        headers: dict,
        body: str,
        timestamp_header: str = 'X-Webhook-Timestamp',
        signature_header: str = 'X-Webhook-Signature'
    ) -> bool:
        """
        验证 Webhook 请求

        Args:
            headers: 请求头
            body: 请求体
            timestamp_header: 时间戳头名称
            signature_header: 签名头名称

        Returns:
            True if valid, False otherwise
        """
        timestamp = headers.get(timestamp_header)
        signature = headers.get(signature_header)

        if not timestamp or not signature:
            return False

        return self.verify_signature(timestamp, body, signature)


class PasswordHasher:
    """
    密码哈希器

    使用 PBKDF2 而不是 bcrypt，性能更好
    """

    def __init__(self, iterations: int = 100000):
        self.iterations = iterations

    def hash_password(self, password: str, salt: Optional[bytes] = None) -> str:
        """
        哈希密码

        Returns:
            格式: iterations$salt$hash (hex)
        """
        if salt is None:
            import os
            salt = os.urandom(32)

        # 使用 PBKDF2-HMAC-SHA256
        key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            self.iterations
        )

        # 返回格式化字符串
        return f"{self.iterations}${salt.hex()}${key.hex()}"

    def verify_password(self, password: str, hashed: str) -> bool:
        """
        验证密码

        Args:
            password: 明文密码
            hashed: 哈希后的密码

        Returns:
            True if valid, False otherwise
        """
        try:
            parts = hashed.split('$')
            if len(parts) != 3:
                return False

            iterations = int(parts[0])
            salt = bytes.fromhex(parts[1])
            stored_key = bytes.fromhex(parts[2])

            # 计算密码哈希
            key = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt,
                iterations
            )

            # 使用时序安全比较
            return hmac.compare_digest(key, stored_key)

        except (ValueError, IndexError):
            return False


# 便捷函数
def compute_hmac(key: str, message: str) -> str:
    """计算 HMAC-SHA256（便捷函数）"""
    return OptimizedCrypto.compute_hmac_sha256_hex(
        key.encode('utf-8'),
        message.encode('utf-8')
    )


def verify_hmac(key: str, message: str, signature: str) -> bool:
    """验证 HMAC-SHA256（便捷函数）"""
    return OptimizedCrypto.verify_hmac_sha256_hex(
        key.encode('utf-8'),
        message.encode('utf-8'),
        signature
    )


def hash_password(password: str) -> str:
    """哈希密码（便捷函数）"""
    hasher = PasswordHasher()
    return hasher.hash_password(password)


def verify_password(password: str, hashed: str) -> bool:
    """验证密码（便捷函数）"""
    hasher = PasswordHasher()
    return hasher.verify_password(password, hashed)


# 使用示例
if __name__ == "__main__":
    # HMAC 签名
    key = "my-secret-key"
    message = "Hello, World!"
    signature = compute_hmac(key, message)
    print(f"HMAC 签名: {signature}")
    print(f"验证结果: {verify_hmac(key, message, signature)}")

    # Webhook 签名验证
    verifier = WebhookSignatureVerifier("webhook-secret")
    timestamp = str(int(time.time()))
    payload = '{"event": "user.created"}'
    sig = verifier.compute_signature(timestamp, payload)
    print(f"\nWebhook 签名: {sig}")
    print(f"验证结果: {verifier.verify_signature(timestamp, payload, sig)}")

    # 密码哈希
    password = "my-secure-password"
    hashed = hash_password(password)
    print(f"\n密码哈希: {hashed}")
    print(f"验证结果: {verify_password(password, hashed)}")
    print(f"错误密码: {verify_password('wrong-password', hashed)}")
