#!/usr/bin/env python3
"""
简化的工具响应格式
基于现有 ExecutionResult 类，为非代码执行工具提供统一响应格式
"""

import json
from typing import Any, Dict, Optional
from dataclasses import dataclass, asdict

@dataclass
class ToolResponse:
    """简化的工具响应格式 - 用于非代码执行的工具"""
    success: bool
    session_id: Optional[str] = None
    data: Optional[Dict[str, Any]] = None       # 工具特定的数据
    message: Optional[str] = None           # 成功时的消息
    error_message: Optional[str] = None     # 失败时的错误
    
    def to_json(self, indent: int = 2, ensure_ascii: bool = False) -> str:
        """转换为JSON字符串"""
        return json.dumps(asdict(self), indent=indent, ensure_ascii=ensure_ascii)
    
    @classmethod
    def create_success(
        cls,
        data: Optional[Dict[str, Any]] = None,
        message: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> 'ToolResponse':
        """创建成功响应"""
        return cls(
            success=True,
            session_id=session_id,
            data=data,
            message=message
        )
    
    @classmethod
    def create_error(
        cls,
        error_message: str,
        session_id: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None
    ) -> 'ToolResponse':
        """创建错误响应"""
        return cls(
            success=False,
            session_id=session_id,
            error_message=error_message,
            data=data
        )
