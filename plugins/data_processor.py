"""
示例插件 - 数据处理插件
演示如何创建和使用Agent Framework插件
"""

import asyncio
import json
import requests
from datetime import datetime
from typing import Dict, List, Any, Callable
from agent_framework.platform.extension_system import BasePlugin, PluginMetadata

class DataProcessorPlugin(BasePlugin):
    """数据处理插件示例"""

    def get_metadata(self) -> PluginMetadata:
        """获取插件元数据"""
        return PluginMetadata(
            name="数据处理插件",
            version="1.0.0",
            description="提供数据清洗、转换、分析等功能",
            author="Agent Framework Team",
            homepage="https://github.com/agent-framework/data-processor-plugin",
            license="MIT",
            dependencies=["requests", "pandas"],
            permissions=["network", "file_system"],
            api_version="1.0",
            tags=["数据处理", "分析", "工具"],
            created_at=datetime(2024, 1, 1),
            updated_at=datetime.now()
        )

    async def initialize(self) -> bool:
        """初始化插件"""
        try:
            # 初始化配置
            self.max_records = self.config.get('max_records', 10000)
            self.cache_enabled = self.config.get('cache_enabled', True)
            self.api_timeout = self.config.get('api_timeout', 30)

            # 初始化缓存
            if self.cache_enabled:
                self.cache = {}

            print(f"数据处理插件初始化成功，最大记录数: {self.max_records}")
            return True

        except Exception as e:
            print(f"数据处理插件初始化失败: {str(e)}")
            return False

    async def cleanup(self) -> bool:
        """清理插件资源"""
        try:
            if hasattr(self, 'cache'):
                self.cache.clear()

            print("数据处理插件清理完成")
            return True

        except Exception as e:
            print(f"数据处理插件清理失败: {str(e)}")
            return False

    def get_api_routes(self) -> List[Dict[str, Any]]:
        """获取插件提供的API路由"""
        return [
            {
                "path": "/api/plugins/data-processor/clean",
                "method": "POST",
                "summary": "清洗数据",
                "description": "对输入数据进行清洗和标准化处理"
            },
            {
                "path": "/api/plugins/data-processor/transform",
                "method": "POST",
                "summary": "转换数据",
                "description": "将数据从一种格式转换为另一种格式"
            },
            {
                "path": "/api/plugins/data-processor/analyze",
                "method": "POST",
                "summary": "分析数据",
                "description": "对数据进行统计分析"
            }
        ]

    def get_hooks(self) -> Dict[str, Callable]:
        """获取插件提供的钩子函数"""
        return {
            "before_data_process": self.before_data_process,
            "after_data_process": self.after_data_process,
            "data_validation": self.validate_data
        }

    def get_tools(self) -> Dict[str, Callable]:
        """获取插件提供的工具函数"""
        return {
            "clean_data": self.clean_data,
            "transform_data": self.transform_data,
            "analyze_data": self.analyze_data,
            "fetch_external_data": self.fetch_external_data,
            "validate_schema": self.validate_schema
        }

    # ==================== 钩子函数 ====================

    def before_data_process(self, data: Any) -> Dict[str, Any]:
        """数据处理前的钩子"""
        return {
            "timestamp": datetime.now().isoformat(),
            "record_count": len(data) if isinstance(data, (list, dict)) else 1,
            "data_type": type(data).__name__
        }

    def after_data_process(self, original_data: Any, processed_data: Any) -> Dict[str, Any]:
        """数据处理后的钩子"""
        return {
            "timestamp": datetime.now().isoformat(),
            "original_count": len(original_data) if isinstance(original_data, (list, dict)) else 1,
            "processed_count": len(processed_data) if isinstance(processed_data, (list, dict)) else 1,
            "processing_success": True
        }

    def validate_data(self, data: Any) -> Dict[str, Any]:
        """数据验证钩子"""
        is_valid = True
        errors = []

        if not data:
            is_valid = False
            errors.append("数据不能为空")

        if isinstance(data, list) and len(data) > self.max_records:
            is_valid = False
            errors.append(f"数据记录数超过限制: {len(data)} > {self.max_records}")

        return {
            "is_valid": is_valid,
            "errors": errors,
            "record_count": len(data) if isinstance(data, (list, dict)) else 1
        }

    # ==================== 工具函数 ====================

    def clean_data(self, data: List[Dict[str, Any]], rules: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """清洗数据"""
        if not rules:
            rules = {
                "remove_nulls": True,
                "trim_strings": True,
                "normalize_case": "lower"
            }

        cleaned_data = []

        for record in data:
            cleaned_record = {}

            for key, value in record.items():
                # 移除空值
                if rules.get("remove_nulls", True) and value is None:
                    continue

                # 处理字符串
                if isinstance(value, str):
                    if rules.get("trim_strings", True):
                        value = value.strip()

                    if rules.get("normalize_case") == "lower":
                        value = value.lower()
                    elif rules.get("normalize_case") == "upper":
                        value = value.upper()

                cleaned_record[key] = value

            if cleaned_record:  # 只添加非空记录
                cleaned_data.append(cleaned_record)

        return cleaned_data

    def transform_data(self, data: List[Dict[str, Any]], mapping: Dict[str, str]) -> List[Dict[str, Any]]:
        """转换数据格式"""
        transformed_data = []

        for record in data:
            transformed_record = {}

            for old_key, new_key in mapping.items():
                if old_key in record:
                    transformed_record[new_key] = record[old_key]

            # 保留未映射的字段
            for key, value in record.items():
                if key not in mapping and key not in transformed_record:
                    transformed_record[key] = value

            transformed_data.append(transformed_record)

        return transformed_data

    def analyze_data(self, data: List[Dict[str, Any]], fields: List[str] = None) -> Dict[str, Any]:
        """分析数据"""
        if not data:
            return {"error": "数据为空"}

        analysis = {
            "total_records": len(data),
            "fields": {},
            "summary": {}
        }

        # 分析字段
        all_fields = set()
        for record in data:
            all_fields.update(record.keys())

        target_fields = fields if fields else list(all_fields)

        for field in target_fields:
            field_values = [record.get(field) for record in data if field in record]
            non_null_values = [v for v in field_values if v is not None]

            field_analysis = {
                "total_count": len(field_values),
                "non_null_count": len(non_null_values),
                "null_count": len(field_values) - len(non_null_values),
                "data_types": list(set(type(v).__name__ for v in non_null_values))
            }

            # 数值分析
            numeric_values = [v for v in non_null_values if isinstance(v, (int, float))]
            if numeric_values:
                field_analysis["numeric_stats"] = {
                    "min": min(numeric_values),
                    "max": max(numeric_values),
                    "avg": sum(numeric_values) / len(numeric_values),
                    "count": len(numeric_values)
                }

            # 字符串分析
            string_values = [v for v in non_null_values if isinstance(v, str)]
            if string_values:
                field_analysis["string_stats"] = {
                    "min_length": min(len(v) for v in string_values),
                    "max_length": max(len(v) for v in string_values),
                    "avg_length": sum(len(v) for v in string_values) / len(string_values),
                    "unique_count": len(set(string_values))
                }

            analysis["fields"][field] = field_analysis

        # 整体摘要
        analysis["summary"] = {
            "total_fields": len(all_fields),
            "analyzed_fields": len(target_fields),
            "avg_fields_per_record": sum(len(record) for record in data) / len(data)
        }

        return analysis

    def fetch_external_data(self, url: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取外部数据"""
        try:
            # 检查缓存
            cache_key = f"{url}_{json.dumps(params, sort_keys=True)}"
            if self.cache_enabled and hasattr(self, 'cache') and cache_key in self.cache:
                return {
                    "success": True,
                    "data": self.cache[cache_key],
                    "from_cache": True
                }

            # 发起请求
            response = requests.get(url, params=params, timeout=self.api_timeout)
            response.raise_for_status()

            data = response.json()

            # 缓存结果
            if self.cache_enabled and hasattr(self, 'cache'):
                self.cache[cache_key] = data

            return {
                "success": True,
                "data": data,
                "from_cache": False,
                "status_code": response.status_code
            }

        except requests.RequestException as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "network_error"
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": "响应不是有效的JSON格式",
                "error_type": "json_error"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "unknown_error"
            }

    def validate_schema(self, data: List[Dict[str, Any]], schema: Dict[str, Any]) -> Dict[str, Any]:
        """验证数据模式"""
        validation_results = {
            "is_valid": True,
            "errors": [],
            "warnings": [],
            "validated_records": 0,
            "failed_records": 0
        }

        required_fields = schema.get("required", [])
        field_types = schema.get("types", {})
        field_constraints = schema.get("constraints", {})

        for i, record in enumerate(data):
            record_errors = []

            # 检查必需字段
            for field in required_fields:
                if field not in record or record[field] is None:
                    record_errors.append(f"记录 {i}: 缺少必需字段 '{field}'")

            # 检查字段类型
            for field, expected_type in field_types.items():
                if field in record and record[field] is not None:
                    actual_type = type(record[field]).__name__
                    if actual_type != expected_type:
                        record_errors.append(
                            f"记录 {i}: 字段 '{field}' 类型错误，期望 {expected_type}，实际 {actual_type}"
                        )

            # 检查字段约束
            for field, constraints in field_constraints.items():
                if field in record and record[field] is not None:
                    value = record[field]

                    # 长度约束
                    if "min_length" in constraints and len(str(value)) < constraints["min_length"]:
                        record_errors.append(
                            f"记录 {i}: 字段 '{field}' 长度小于最小值 {constraints['min_length']}"
                        )

                    if "max_length" in constraints and len(str(value)) > constraints["max_length"]:
                        record_errors.append(
                            f"记录 {i}: 字段 '{field}' 长度大于最大值 {constraints['max_length']}"
                        )

                    # 数值约束
                    if isinstance(value, (int, float)):
                        if "min_value" in constraints and value < constraints["min_value"]:
                            record_errors.append(
                                f"记录 {i}: 字段 '{field}' 值小于最小值 {constraints['min_value']}"
                            )

                        if "max_value" in constraints and value > constraints["max_value"]:
                            record_errors.append(
                                f"记录 {i}: 字段 '{field}' 值大于最大值 {constraints['max_value']}"
                            )

            if record_errors:
                validation_results["errors"].extend(record_errors)
                validation_results["failed_records"] += 1
                validation_results["is_valid"] = False
            else:
                validation_results["validated_records"] += 1

        return validation_results