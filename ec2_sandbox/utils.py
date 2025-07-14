#!/usr/bin/env python3
"""
EC2 Sandbox 工具函数
通用工具函数和日志配置
"""

import json
import hashlib
import time
import re
import logging
import os
from typing import Dict, Any, Optional, List
from logging.handlers import RotatingFileHandler
import boto3


def get_logger(name: str, log_file: Optional[str] = 'ec2_sandbox.log') -> logging.Logger:
    """
    获取配置好的logger实例
    
    Args:
        name: logger名称
        log_file: 日志文件名（可选），如果不提供则只输出到控制台
    
    Returns:
        配置好的logger实例
    """
    logger = logging.getLogger(name)
    
    # 避免重复配置
    if logger.handlers:
        return logger
    
    logger.setLevel(logging.INFO)
    
    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器（如果指定了日志文件）
    if log_file:
        log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
        os.makedirs(log_dir, exist_ok=True)
        
        log_path = os.path.join(log_dir, log_file)
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    # 防止日志传播到根logger（避免重复）
    logger.propagate = False
    
    return logger

# 设置第三方库日志级别
logging.getLogger('botocore').setLevel(logging.WARNING)
logging.getLogger('boto3').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

# 为当前模块创建logger
logger = get_logger(__name__)


def is_safe_filename(filename: str) -> bool:
    """检查文件名是否安全"""
    # 检查文件名长度
    if len(filename) > 255:
        return False
    
    # 检查危险字符和模式
    dangerous_patterns = [
        r'\.\./+',  # 路径遍历
        r'\.\.\\+', # Windows路径遍历
        r'^/',      # 绝对路径
        r'^\\',     # Windows绝对路径
        r'[|&;$`<>]',  # Shell特殊字符
        r'[\x00-\x1f]', # 控制字符
    ]
    
    for pattern in dangerous_patterns:
        if re.search(pattern, filename):
            return False
    
    # 检查保留名称（Windows）
    reserved_names = ['CON', 'PRN', 'AUX', 'NUL'] + [f'COM{i}' for i in range(1, 10)] + [f'LPT{i}' for i in range(1, 10)]
    if filename.upper().split('.')[0] in reserved_names:
        return False
    
    # 只允许字母、数字、点、下划线、连字符
    if not re.match(r'^[a-zA-Z0-9._-]+$', filename):
        return False
    
    return True


def sanitize_env_var(key: str, value: str) -> tuple[str, str]:
    """清理环境变量，防止注入攻击"""
    # 检查环境变量名
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', key):
        raise ValueError(f"Invalid environment variable name: {key}")
    
    # 检查环境变量值中的危险字符
    dangerous_chars = ['`', '$', '\\', '"', "'", ';', '&', '|', '<', '>']
    for char in dangerous_chars:
        if char in value:
            # 转义危险字符
            value = value.replace(char, f'\\{char}')
    
    return key, value


def generate_task_hash(task_data: Dict[str, Any]) -> str:
    """基于任务属性生成hash"""
    # 包含代码、运行时、时间戳等信息
    hash_data = {
        "code": task_data.get("code", ""),
        "runtime": task_data.get("runtime", "python"),
        "session_id": task_data.get("session_id", ""),
        "timestamp": int(time.time() // 3600)  # 按小时分组
    }
    
    hash_string = json.dumps(hash_data, sort_keys=True)
    return hashlib.sha256(hash_string.encode()).hexdigest()[:16]


def parse_file_list(file_section: str) -> List[str]:
    """解析文件列表"""
    files = []
    lines = file_section.strip().split('\n')
    for line in lines:
        if line.startswith('-') or line.startswith('d'):
            # ls -la 格式的行
            parts = line.split()
            if len(parts) >= 9:
                filename = ' '.join(parts[8:])
                if filename not in ['.', '..']:
                    files.append(filename)
    return files


def create_aws_client(service: str, region: str, aws_profile: Optional[str] = None, 
                     access_key_id: Optional[str] = None, secret_access_key: Optional[str] = None,
                     session_token: Optional[str] = None):
    """创建AWS客户端的通用函数"""
    
    if aws_profile:
        session = boto3.Session(profile_name=aws_profile)
        return session.client(service, region_name=region)
    elif access_key_id and secret_access_key:
        client_kwargs = {
            "aws_access_key_id": access_key_id,
            "aws_secret_access_key": secret_access_key,
            "region_name": region
        }
        if session_token:
            client_kwargs["aws_session_token"] = session_token
        return boto3.client(service, **client_kwargs)
    else:
        return boto3.client(service, region_name=region)
