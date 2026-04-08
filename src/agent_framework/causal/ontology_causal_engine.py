#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本体论驱动的因果推理引擎 - Palantir Ontology Integration

核心概念：
1. 本体论（Ontology）：定义实体类型、属性和关系的结构化知识模型
2. 对象类型（Object Types）：定义领域内的实体类别
3. 属性（Properties）：描述对象的特征
4. 链接类型（Link Types）：定义对象之间的关系
5. 因果推理：基于本体论结构进行因果分析

Palantir 本体论特性：
- 类型系统：强类型的对象和关系定义
- 属性继承：支持对象类型的层次结构
- 关系约束：定义哪些对象类型可以通过哪些链接类型连接
- 时间感知：支持时间维度的因果追踪
- 动作系统：定义可以在对象上执行的操作
"""

from __future__ import annotations
import agent_framework.core.fast_json as json
import uuid
import time
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from datetime import datetime


# ═══════════════════════════════════════════════════════════════════════════
# 枚举类型
# ═══════════════════════════════════════════════════════════════════════════

class PropertyType(Enum):
    """属性类型"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    ARRAY = "array"
    OBJECT = "object"


class CausalStrength(Enum):
    """因果强度"""
    DETERMINISTIC = (1.0, "确定性")
    STRONG = (0.8, "强")
    MODERATE = (0.6, "中等")
    WEAK = (0.4, "弱")
    NEGLIGIBLE = (0.2, "可忽略")

    @property
    def value_float(self) -> float:
        return self.value[0]

    @property
    def label(self) -> str:
        return self.value[1]


# ═══════════════════════════════════════════════════════════════════════════
# 本体论核心数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PropertyDefinition:
    """属性定义"""
    id: str
    name: str
    property_type: PropertyType
    description: str = ""
    required: bool = False
    default_value: Any = None
    constraints: Dict[str, Any] = field(default_factory=dict)

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """验证属性值"""
        if value is None:
            if self.required:
                return False, f"属性 {self.name} 是必需的"
            return True, None

        type_map = {
            PropertyType.STRING: str,
            PropertyType.INTEGER: int,
            PropertyType.FLOAT: (int, float),
            PropertyType.BOOLEAN: bool,
            PropertyType.ARRAY: list,
            PropertyType.OBJECT: dict
        }

        expected_type = type_map.get(self.property_type)
        if expected_type and not isinstance(value, expected_type):
            return False, f"属性 {self.name} 类型错误"

        if "min" in self.constraints and value < self.constraints["min"]:
            return False, f"属性 {self.name} 小于最小值"
        if "max" in self.constraints and value > self.constraints["max"]:
            return False, f"属性 {self.name} 大于最大值"

        return True, None


@dataclass
class ObjectType:
    """对象类型（Palantir Object Type）"""
    id: str
    name: str
    description: str
    properties: Dict[str, PropertyDefinition] = field(default_factory=dict)
    parent_types: List[str] = field(default_factory=list)
    icon: str = "📦"
    color: str = "#3498db"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_property(self, prop: PropertyDefinition):
        """添加属性"""
        self.properties[prop.id] = prop

    def get_all_properties(self, type_registry: Dict[str, 'ObjectType']) -> Dict[str, PropertyDefinition]:
        """获取所有属性（包括继承的）"""
        all_props = {}
        for parent_id in self.parent_types:
            if parent_id in type_registry:
                parent_props = type_registry[parent_id].get_all_properties(type_registry)
                all_props.update(parent_props)
        all_props.update(self.properties)
        return all_props


@dataclass
class LinkType:
    """链接类型（Palantir Link Type）"""
    id: str
    name: str
    description: str
    source_types: List[str]
    target_types: List[str]
    causal_strength: Optional[CausalStrength] = None
    properties: Dict[str, PropertyDefinition] = field(default_factory=dict)
    bidirectional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_link(self, source_type: str, target_type: str) -> bool:
        """检查是否可以连接"""
        return source_type in self.source_types and target_type in self.target_types

    def is_causal(self) -> bool:
        """是否是因果关系"""
        return self.causal_strength is not None


@dataclass
class OntologyObject:
    """本体论对象实例"""
    id: str
    type_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_property(self, prop_id: str, default: Any = None) -> Any:
        """获取属性值"""
        return self.properties.get(prop_id, default)

    def set_property(self, prop_id: str, value: Any):
        """设置属性值"""
        self.properties[prop_id] = value
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }


@dataclass
class OntologyLink:
    """本体论链接实例"""
    id: str
    type_id: str
    source_id: str
    target_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": self.properties,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata
        }


@dataclass
class ActionDefinition:
    """动作定义（Palantir Action）"""
    id: str
    name: str
    description: str
    object_types: List[str]
    parameters: Dict[str, PropertyDefinition] = field(default_factory=dict)
    causal_effects: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_apply_to(self, object_type: str) -> bool:
        """检查是否可以应用到对象类型"""
        return object_type in self.object_types


# ═══════════════════════════════════════════════════════════════════════════
# 本体论管理器
# ═══════════════════════════════════════════════════════════════════════════

class Ontology:
    """本体论管理器（Palantir Ontology）"""

    def __init__(self):
        self.object_types: Dict[str, ObjectType] = {}
        self.link_types: Dict[str, LinkType] = {}
        self.objects: Dict[str, OntologyObject] = {}
        self.links: Dict[str, OntologyLink] = {}
        self.actions: Dict[str, ActionDefinition] = {}
        self.metadata = {
            "created_at": time.time(),
            "version": "1.0.0",
            "description": "Ontology-driven causal reasoning system"
        }

    # ─── 类型管理 ──────────────────────────────────────────────────────────

    def register_object_type(self, obj_type: ObjectType) -> bool:
        """注册对象类型"""
        if obj_type.id in self.object_types:
            return False
        self.object_types[obj_type.id] = obj_type
        return True

    def register_link_type(self, link_type: LinkType) -> bool:
        """注册链接类型"""
        if link_type.id in self.link_types:
            return False
        self.link_types[link_type.id] = link_type
        return True

    def register_action(self, action: ActionDefinition) -> bool:
        """注册动作"""
        if action.id in self.actions:
            return False
        self.actions[action.id] = action
        return True

    # ─── 对象管理 ──────────────────────────────────────────────────────────

    def create_object(
        self,
        type_id: str,
        properties: Dict[str, Any],
        object_id: Optional[str] = None
    ) -> Optional[OntologyObject]:
        """创建对象实例"""
        if type_id not in self.object_types:
            return None

        obj_type = self.object_types[type_id]
        obj_id = object_id or str(uuid.uuid4())

        # 验证属性
        all_props = obj_type.get_all_properties(self.object_types)
        for prop_id, prop_def in all_props.items():
            if prop_id in properties:
                valid, error = prop_def.validate(properties[prop_id])
                if not valid:
                    raise ValueError(error)

        obj = OntologyObject(
            id=obj_id,
            type_id=type_id,
            properties=properties
        )
        self.objects[obj_id] = obj
        return obj

    def get_object(self, object_id: str) -> Optional[OntologyObject]:
        """获取对象"""
        return self.objects.get(object_id)

    def update_object(self, object_id: str, properties: Dict[str, Any]) -> bool:
        """更新对象属性"""
        obj = self.get_object(object_id)
        if not obj:
            return False

        for key, value in properties.items():
            obj.set_property(key, value)
        return True

    def delete_object(self, object_id: str) -> bool:
        """删除对象"""
        if object_id in self.objects:
            # 删除相关链接
            links_to_delete = [
                link_id for link_id, link in self.links.items()
                if link.source_id == object_id or link.target_id == object_id
            ]
            for link_id in links_to_delete:
                del self.links[link_id]

            del self.objects[object_id]
            return True
        return False

    # ─── 链接管理 ──────────────────────────────────────────────────────────

    def create_link(
        self,
        type_id: str,
        source_id: str,
        target_id: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.8,
        link_id: Optional[str] = None
    ) -> Optional[OntologyLink]:
        """创建链接实例"""
        if type_id not in self.link_types:
            return None

        link_type = self.link_types[type_id]

        # 验证源和目标对象
        source_obj = self.get_object(source_id)
        target_obj = self.get_object(target_id)
        if not source_obj or not target_obj:
            return None

        # 验证链接类型约束
        if not link_type.can_link(source_obj.type_id, target_obj.type_id):
            return None

        link_id = link_id or str(uuid.uuid4())
        link = OntologyLink(
            id=link_id,
            type_id=type_id,
            source_id=source_id,
            target_id=target_id,
            properties=properties or {},
            confidence=confidence
        )
        self.links[link_id] = link
        return link

    def get_link(self, link_id: str) -> Optional[OntologyLink]:
        """获取链接"""
        return self.links.get(link_id)

    def get_links_from(self, object_id: str, link_type: Optional[str] = None) -> List[OntologyLink]:
        """获取从对象出发的链接"""
        links = [
            link for link in self.links.values()
            if link.source_id == object_id
        ]
        if link_type:
            links = [link for link in links if link.type_id == link_type]
        return links

    def get_links_to(self, object_id: str, link_type: Optional[str] = None) -> List[OntologyLink]:
        """获取指向对象的链接"""
        links = [
            link for link in self.links.values()
            if link.target_id == object_id
        ]
        if link_type:
            links = [link for link in links if link.type_id == link_type]
        return links

    def delete_link(self, link_id: str) -> bool:
        """删除链接"""
        if link_id in self.links:
            del self.links[link_id]
            return True
        return False

    def validate(self, value: Any) -> Tuple[bool, Optional[str]]:
        """验证属性值"""
        if value is None:
            if self.required:
                return False, f"属性 {self.name} 是必需的"
            return True, None

        type_map = {
            PropertyType.STRING: str,
            PropertyType.INTEGER: int,
            PropertyType.FLOAT: (int, float),
            PropertyType.BOOLEAN: bool,
            PropertyType.ARRAY: list,
            PropertyType.OBJECT: dict
        }

        expected_type = type_map.get(self.property_type)
        if expected_type and not isinstance(value, expected_type):
            return False, f"属性 {self.name} 类型错误"

        if "min" in self.constraints and value < self.constraints["min"]:
            return False, f"属性 {self.name} 小于最小值"
        if "max" in self.constraints and value > self.constraints["max"]:
            return False, f"属性 {self.name} 大于最大值"

        return True, None


@dataclass
class ObjectType:
    """对象类型（Palantir Object Type）"""
    id: str
    name: str
    description: str
    properties: Dict[str, PropertyDefinition] = field(default_factory=dict)
    parent_types: List[str] = field(default_factory=list)
    icon: str = "📦"
    color: str = "#3498db"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_property(self, prop: PropertyDefinition):
        """添加属性"""
        self.properties[prop.id] = prop

    def get_all_properties(self, type_registry: Dict[str, 'ObjectType']) -> Dict[str, PropertyDefinition]:
        """获取所有属性（包括继承的）"""
        all_props = {}
        for parent_id in self.parent_types:
            if parent_id in type_registry:
                parent_props = type_registry[parent_id].get_all_properties(type_registry)
                all_props.update(parent_props)
        all_props.update(self.properties)
        return all_props


@dataclass
class LinkType:
    """链接类型（Palantir Link Type）"""
    id: str
    name: str
    description: str
    source_types: List[str]
    target_types: List[str]
    causal_strength: Optional[CausalStrength] = None
    properties: Dict[str, PropertyDefinition] = field(default_factory=dict)
    bidirectional: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_link(self, source_type: str, target_type: str) -> bool:
        """检查是否可以连接"""
        return source_type in self.source_types and target_type in self.target_types

    def is_causal(self) -> bool:
        """是否是因果关系"""
        return self.causal_strength is not None


@dataclass
class OntologyObject:
    """本体论对象实例"""
    id: str
    type_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_property(self, prop_id: str, default: Any = None) -> Any:
        """获取属性值"""
        return self.properties.get(prop_id, default)

    def set_property(self, prop_id: str, value: Any):
        """设置属性值"""
        self.properties[prop_id] = value
        self.updated_at = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "properties": self.properties,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata
        }


@dataclass
class OntologyLink:
    """本体论链接实例"""
    id: str
    type_id: str
    source_id: str
    target_id: str
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type_id": self.type_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "properties": self.properties,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "metadata": self.metadata
        }


@dataclass
class ActionDefinition:
    """动作定义（Palantir Action）"""
    id: str
    name: str
    description: str
    object_types: List[str]
    parameters: Dict[str, PropertyDefinition] = field(default_factory=dict)
    causal_effects: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def can_apply_to(self, object_type: str) -> bool:
        """检查是否可以应用到对象类型"""
        return object_type in self.object_types


# ═══════════════════════════════════════════════════════════════════════════
# 本体论管理器
# ═══════════════════════════════════════════════════════════════════════════

class Ontology:
    """本体论管理器（Palantir Ontology）"""

    def __init__(self):
        self.object_types: Dict[str, ObjectType] = {}
        self.link_types: Dict[str, LinkType] = {}
        self.objects: Dict[str, OntologyObject] = {}
        self.links: Dict[str, OntologyLink] = {}
        self.actions: Dict[str, ActionDefinition] = {}
        self.metadata = {
            "created_at": time.time(),
            "version": "1.0.0",
            "description": "Ontology-driven causal reasoning system"
        }

    # ─── 类型管理 ──────────────────────────────────────────────────────────

    def register_object_type(self, obj_type: ObjectType) -> bool:
        """注册对象类型"""
        if obj_type.id in self.object_types:
            return False
        self.object_types[obj_type.id] = obj_type
        return True

    def register_link_type(self, link_type: LinkType) -> bool:
        """注册链接类型"""
        if link_type.id in self.link_types:
            return False
        self.link_types[link_type.id] = link_type
        return True

    def register_action(self, action: ActionDefinition) -> bool:
        """注册动作"""
        if action.id in self.actions:
            return False
        self.actions[action.id] = action
        return True

    # ─── 对象管理 ──────────────────────────────────────────────────────────

    def create_object(
        self,
        type_id: str,
        properties: Dict[str, Any],
        object_id: Optional[str] = None
    ) -> Optional[OntologyObject]:
        """创建对象实例"""
        if type_id not in self.object_types:
            return None

        obj_type = self.object_types[type_id]
        obj_id = object_id or str(uuid.uuid4())

        # 验证属性
        all_props = obj_type.get_all_properties(self.object_types)
        for prop_id, prop_def in all_props.items():
            if prop_id in properties:
                valid, error = prop_def.validate(properties[prop_id])
                if not valid:
                    raise ValueError(error)

        obj = OntologyObject(
            id=obj_id,
            type_id=type_id,
            properties=properties
        )
        self.objects[obj_id] = obj
        return obj

    def get_object(self, object_id: str) -> Optional[OntologyObject]:
        """获取对象"""
        return self.objects.get(object_id)

    def update_object(self, object_id: str, properties: Dict[str, Any]) -> bool:
        """更新对象属性"""
        obj = self.get_object(object_id)
        if not obj:
            return False

        for key, value in properties.items():
            obj.set_property(key, value)
        return True

    def delete_object(self, object_id: str) -> bool:
        """删除对象"""
        if object_id in self.objects:
            # 删除相关链接
            links_to_delete = [
                link_id for link_id, link in self.links.items()
                if link.source_id == object_id or link.target_id == object_id
            ]
            for link_id in links_to_delete:
                del self.links[link_id]

            del self.objects[object_id]
            return True
        return False

    # ─── 链接管理 ──────────────────────────────────────────────────────────

    def create_link(
        self,
        type_id: str,
        source_id: str,
        target_id: str,
        properties: Optional[Dict[str, Any]] = None,
        confidence: float = 0.8,
        link_id: Optional[str] = None
    ) -> Optional[OntologyLink]:
        """创建链接实例"""
        if type_id not in self.link_types:
            return None

        link_type = self.link_types[type_id]

        # 验证源和目标对象
        source_obj = self.get_object(source_id)
        target_obj = self.get_object(target_id)
        if not source_obj or not target_obj:
            return None

        # 验证链接类型约束
        if not link_type.can_link(source_obj.type_id, target_obj.type_id):
            return None

        link_id = link_id or str(uuid.uuid4())
        link = OntologyLink(
            id=link_id,
            type_id=type_id,
            source_id=source_id,
            target_id=target_id,
            properties=properties or {},
            confidence=confidence
        )
        self.links[link_id] = link
        return link

    def get_link(self, link_id: str) -> Optional[OntologyLink]:
        """获取链接"""
        return self.links.get(link_id)

    def get_links_from(self, object_id: str, link_type: Optional[str] = None) -> List[OntologyLink]:
        """获取从对象出发的链接"""
        links = [
            link for link in self.links.values()
            if link.source_id == object_id
        ]
        if link_type:
            links = [link for link in links if link.type_id == link_type]
        return links

    def get_links_to(self, object_id: str, link_type: Optional[str] = None) -> List[OntologyLink]:
        """获取指向对象的链接"""
        links = [
            link for link in self.links.values()
            if link.target_id == object_id
        ]
        if link_type:
            links = [link for link in links if link.type_id == link_type]
        return links

    def delete_link(self, link_id: str) -> bool:
        """删除链接"""
        if link_id in self.links:
            del self.links[link_id]
            return True
        return False
