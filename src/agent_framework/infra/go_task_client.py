"""
Go 异步任务系统 - Python 客户端
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

import requests


class GoTaskExecutor:
    """Go 任务执行器客户端"""

    def __init__(self, base_url: str = "http://localhost:8080", timeout: float = 5.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self._last_health_check = 0.0
        self._last_health_status = False

    def _get(self, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        return self.session.get(f"{self.base_url}{path}", timeout=timeout, **kwargs)

    def _post(self, path: str, **kwargs) -> requests.Response:
        timeout = kwargs.pop("timeout", self.timeout)
        return self.session.post(f"{self.base_url}{path}", timeout=timeout, **kwargs)

    def submit_task(
        self,
        task_type: str,
        params: Dict[str, Any],
        priority: int = 0,
    ) -> str:
        response = self._post(
            "/submit",
            json={
                "task_type": task_type,
                "params": params,
                "priority": priority,
            },
        )
        response.raise_for_status()
        return response.json()["task_id"]

    def get_task(self, task_id: str) -> Dict[str, Any]:
        response = self._get(f"/tasks/{task_id}")
        response.raise_for_status()
        return response.json()

    def get_task_status(self, task_id: str) -> Dict[str, Any]:
        response = self._get(f"/tasks/{task_id}/status")
        response.raise_for_status()
        return response.json()

    def get_task_result(self, task_id: str) -> Dict[str, Any]:
        response = self._get(f"/tasks/{task_id}/result")
        response.raise_for_status()
        return response.json()

    def cancel_task(self, task_id: str) -> bool:
        response = self._post(f"/tasks/{task_id}/cancel")
        if response.status_code >= 400:
            return False
        return True

    def list_tasks(self, status: Optional[str] = None, limit: int = 100) -> Dict[str, Any]:
        params = {"limit": limit}
        if status:
            params["status"] = status
        response = self._get("/tasks", params=params)
        response.raise_for_status()
        return response.json()

    def get_statistics(self) -> Dict[str, Any]:
        response = self._get("/statistics")
        response.raise_for_status()
        return response.json()

    def clear_completed(self, older_than: Optional[float] = None) -> Dict[str, Any]:
        params = {}
        if older_than is not None:
            params["older_than"] = older_than
        response = self._post("/clear", params=params)
        response.raise_for_status()
        return response.json()

    def wait_for_task(
        self,
        task_id: str,
        timeout: float = 60.0,
        poll_interval: float = 0.5,
    ) -> Dict[str, Any]:
        start_time = time.time()
        while time.time() - start_time < timeout:
            task = self.get_task(task_id)
            if task["status"] in {"completed", "failed", "cancelled"}:
                return task
            time.sleep(poll_interval)
        raise TimeoutError(f"Task {task_id} did not complete within {timeout} seconds")

    def submit_and_wait(
        self,
        task_type: str,
        params: Dict[str, Any],
        priority: int = 0,
        timeout: float = 60.0,
    ) -> Dict[str, Any]:
        task_id = self.submit_task(task_type, params, priority)
        return self.wait_for_task(task_id, timeout=timeout)

    def health_check(self, force: bool = False, cache_ttl: float = 2.0) -> bool:
        now = time.time()
        if not force and (now - self._last_health_check) < cache_ttl:
            return self._last_health_status
        try:
            response = self._get("/health", timeout=min(self.timeout, 0.2))
            self._last_health_status = response.status_code == 200
        except requests.RequestException:
            self._last_health_status = False
        self._last_health_check = now
        return self._last_health_status


_executor: Optional[GoTaskExecutor] = None


def get_task_executor(base_url: str = "http://localhost:8080") -> GoTaskExecutor:
    """获取 Go 任务执行器单例"""
    global _executor
    if _executor is None or _executor.base_url != base_url.rstrip("/"):
        _executor = GoTaskExecutor(base_url)
    return _executor
