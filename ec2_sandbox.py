#!/usr/bin/env python3
"""
EC2 Sandbox 核心功能
基于EC2实例的代码执行沙箱工具 - 核心实现
"""

import os
import json
import hashlib
import subprocess
import tempfile
import shutil
import time
import logging
import re
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
import boto3
from botocore.exceptions import ClientError, NoCredentialsError

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logging.getLogger('botocore').setLevel(logging.WARNING)

@dataclass
class ExecutionResult:
    """代码执行结果"""
    success: bool
    stdout: str
    stderr: str
    return_code: int
    execution_time: float
    working_directory: str
    files_created: List[str]
    task_hash: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class SandboxConfig:
    """沙箱配置"""
    instance_id: str
    region: str
    aws_profile: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    base_sandbox_dir: str = "/opt/sandbox"
    max_execution_time: int = 300  # 5分钟
    max_memory_mb: int = 1024
    cleanup_after_hours: int = 24
    allowed_runtimes: List[str] = None

    def __post_init__(self):
        if self.allowed_runtimes is None:
            self.allowed_runtimes = ["python3", "python", "node", "bash", "sh"]


class EC2SandboxEnv:
    """EC2沙盒环境 - 单例，对应一个EC2实例，负责基础设施管理"""
    
    _instances = {}  # 按配置缓存环境实例
    
    def __new__(cls, config: SandboxConfig):
        # 基于实例ID创建唯一的环境实例
        instance_key = f"{config.instance_id}_{config.region}"
        
        if instance_key not in cls._instances:
            logger.info(f"初始化EC2沙盒环境: {config.instance_id}")
            instance = super().__new__(cls)
            cls._instances[instance_key] = instance
        else:
            logger.debug(f"复用现有EC2沙盒环境: {config.instance_id}")
            
        return cls._instances[instance_key]
    
    def __init__(self, config: SandboxConfig):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
            
        self.config = config
        self.ec2_client = self._create_ec2_client()
        self.ssm_client = self._create_ssm_client()
        self._ensure_base_directory()
        self._initialized = True
        logger.info(f"EC2沙盒环境初始化完成: {config.instance_id}")
    
    def create_sandbox_instance(self, task_id: str = None) -> 'SandboxInstance':
        """在环境中创建一个沙盒实例"""
        return SandboxInstance(self, task_id)
        
    def _create_ec2_client(self):
        """创建EC2客户端"""
        session_kwargs = {"region_name": self.config.region}
        
        if self.config.aws_profile:
            session = boto3.Session(profile_name=self.config.aws_profile)
            return session.client('ec2', **session_kwargs)
        elif self.config.access_key_id and self.config.secret_access_key:
            session_kwargs.update({
                "aws_access_key_id": self.config.access_key_id,
                "aws_secret_access_key": self.config.secret_access_key
            })
            if self.config.session_token:
                session_kwargs["aws_session_token"] = self.config.session_token
            return boto3.client('ec2', **session_kwargs)
        else:
            return boto3.client('ec2', **session_kwargs)
    
    def _create_ssm_client(self):
        """创建SSM客户端用于远程执行"""
        session_kwargs = {"region_name": self.config.region}
        
        if self.config.aws_profile:
            session = boto3.Session(profile_name=self.config.aws_profile)
            return session.client('ssm', **session_kwargs)
        elif self.config.access_key_id and self.config.secret_access_key:
            session_kwargs.update({
                "aws_access_key_id": self.config.access_key_id,
                "aws_secret_access_key": self.config.secret_access_key
            })
            if self.config.session_token:
                session_kwargs["aws_session_token"] = self.config.session_token
            return boto3.client('ssm', **session_kwargs)
        else:
            return boto3.client('ssm', **session_kwargs)
    
    def _ensure_base_directory(self):
        """确保基础沙箱目录存在"""
        try:
            command = f"sudo mkdir -p {self.config.base_sandbox_dir} && sudo chmod 755 {self.config.base_sandbox_dir}"
            self._execute_remote_command(command)
        except Exception as e:
            logger.warning(f"Failed to create base directory: {e}")
    
    def _generate_task_hash(self, task_data: Dict[str, Any]) -> str:
        """基于任务属性生成hash"""
        # 包含代码、运行时、时间戳等信息
        hash_data = {
            "code": task_data.get("code", ""),
            "runtime": task_data.get("runtime", "python3"),
            "session_id": task_data.get("session_id", ""),
            "timestamp": int(time.time() // 3600)  # 按小时分组
        }
        
        hash_string = json.dumps(hash_data, sort_keys=True)
        return hashlib.sha256(hash_string.encode()).hexdigest()[:16]
    
    def _is_safe_filename(self, filename: str) -> bool:
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
    
    def _sanitize_env_var(self, key: str, value: str) -> tuple[str, str]:
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
    
    def _create_task_filesystem(self, task_hash: str, files: Optional[Dict[str, str]] = None) -> str:
        """创建任务专用文件系统"""
        task_dir = f"{self.config.base_sandbox_dir}/{task_hash}"
        
        # 创建目录
        commands = [
            f"mkdir -p {task_dir}",
            f"chmod 755 {task_dir}",
            f"cd {task_dir}"
        ]
        
        # 如果提供了文件，创建文件
        if files:
            for filename, content in files.items():
                # 安全的文件名检查
                if not self._is_safe_filename(filename):
                    raise ValueError(f"Unsafe filename: {filename}")
                
                try:
                    # 使用base64编码来避免特殊字符问题
                    encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
                    commands.append(f"echo '{encoded_content}' | base64 -d > '{filename}'")
                except Exception as e:
                    logger.error(f"Failed to encode file {filename}: {e}")
                    raise ValueError(f"Failed to process file {filename}: {e}")
        
        # 执行命令
        full_command = " && ".join(commands)
        result = self._execute_remote_command(full_command)
        
        # 检查目录创建是否成功
        if result['return_code'] != 0:
            raise RuntimeError(f"Failed to create task filesystem: {result['stderr']}")
        
        return task_dir
    
    def _execute_remote_command(self, command: str, working_dir: Optional[str] = None) -> Dict[str, Any]:
        """在EC2实例上执行命令"""
        try:
            # 如果指定了工作目录，添加cd命令
            if working_dir:
                command = f"cd {working_dir} && {command}"
            
            response = self.ssm_client.send_command(
                InstanceIds=[self.config.instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={
                    'commands': [command]  # 确保是列表格式
                },
                TimeoutSeconds=min(self.config.max_execution_time, 3600)  # 限制最大超时时间
            )
            
            command_id = response['Command']['CommandId']
            
            # 等待命令执行完成，增加超时处理
            waiter = self.ssm_client.get_waiter('command_executed')
            max_attempts = max(30, self.config.max_execution_time // 2)  # 动态调整等待次数
            waiter.wait(
                CommandId=command_id,
                InstanceId=self.config.instance_id,
                WaiterConfig={
                    'Delay': 2,
                    'MaxAttempts': max_attempts
                }
            )
            
            # 获取执行结果
            result = self.ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=self.config.instance_id
            )
            
            return {
                'stdout': result.get('StandardOutputContent', ''),
                'stderr': result.get('StandardErrorContent', ''),
                'status': result.get('Status', 'Unknown'),
                'return_code': result.get('ResponseCode', -1)
            }
            
        except Exception as e:
            logger.error(f"Remote command execution failed: {e}")
            return {
                'stdout': '',
                'stderr': str(e),
                'status': 'Failed',
                'return_code': 1
            }
    
    def check_instance_status(self) -> Dict[str, Any]:
        """检查EC2实例状态"""
        try:
            response = self.ec2_client.describe_instances(
                InstanceIds=[self.config.instance_id]
            )
            
            if response['Reservations']:
                instance = response['Reservations'][0]['Instances'][0]
                return {
                    'instance_id': instance['InstanceId'],
                    'state': instance['State']['Name'],
                    'instance_type': instance['InstanceType'],
                    'public_ip': instance.get('PublicIpAddress'),
                    'private_ip': instance.get('PrivateIpAddress'),
                    'launch_time': instance['LaunchTime'].isoformat()
                }
            else:
                return {'error': 'Instance not found'}
                
        except Exception as e:
            return {'error': str(e)}
    
    def cleanup_old_tasks(self, hours: Optional[int] = None):
        """清理过期的任务目录"""
        cleanup_hours = hours or self.config.cleanup_after_hours
        
        try:
            # 查找并删除过期目录
            # 使用-mmin而不是-mtime来更精确地控制时间
            cleanup_minutes = cleanup_hours * 60
            command = f"""
            find {self.config.base_sandbox_dir} -maxdepth 1 -type d -mmin +{cleanup_minutes} ! -path {self.config.base_sandbox_dir} -exec rm -rf {{}} + 2>/dev/null || true
            """
            
            result = self._execute_remote_command(command)
            logger.info(f"Cleanup completed for tasks older than {cleanup_hours} hours")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def _get_task_files_by_hash(self, task_hash: str, filename: Optional[str] = None) -> Dict[str, str]:
        """根据task_hash获取任务目录中的文件内容"""
        task_dir = f"{self.config.base_sandbox_dir}/{task_hash}"
        files_content = {}
        
        try:
            if filename:
                # 获取特定文件
                command = f"cat {task_dir}/{filename}"
                result = self._execute_remote_command(command)
                if result['return_code'] == 0:
                    files_content[filename] = result['stdout']
            else:
                # 获取所有文件
                list_command = f"find {task_dir} -type f -exec basename {{}} \\;"
                list_result = self._execute_remote_command(list_command)
                
                if list_result['return_code'] == 0:
                    filenames = list_result['stdout'].strip().split('\n')
                    for fname in filenames:
                        if fname:
                            cat_command = f"cat {task_dir}/{fname}"
                            cat_result = self._execute_remote_command(cat_command)
                            if cat_result['return_code'] == 0:
                                files_content[fname] = cat_result['stdout']
            
        except Exception as e:
            logger.error(f"Failed to get task files: {e}")
        
        return files_content
    
    def _parse_file_list(self, file_section: str) -> List[str]:
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


class SandboxInstance:
    """沙盒实例 - 每个任务一个，负责具体的代码执行和文件管理"""
    
    def __init__(self, environment: EC2SandboxEnv, task_id: str = None):
        self.environment = environment
        self.task_id = task_id or f"task_{int(time.time())}"
        self.task_hash = None  # 当前任务的hash
        logger.debug(f"创建沙盒实例: {self.task_id}")
    
    def execute_code(
        self,
        code: str,
        runtime: str = "python3",
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        create_filesystem: bool = True
    ) -> ExecutionResult:
        """在此沙盒实例中执行代码"""
        start_time = time.time()
        
        # 验证运行时
        if runtime not in self.environment.config.allowed_runtimes:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Runtime '{runtime}' not allowed. Allowed: {self.environment.config.allowed_runtimes}",
                return_code=1,
                execution_time=0,
                working_directory="",
                files_created=[],
                task_hash=None,
                error_message=f"Invalid runtime: {runtime}"
            )
        
        try:
            # 生成任务hash
            task_data = {
                "code": code,
                "runtime": runtime,
                "session_id": self.task_id
            }
            self.task_hash = self.environment._generate_task_hash(task_data)
            
            # 创建文件系统
            working_dir = ""
            if create_filesystem:
                working_dir = self.environment._create_task_filesystem(self.task_hash, files)
            
            # 准备执行命令
            exec_commands = []
            
            # 设置环境变量
            if env_vars:
                for key, value in env_vars.items():
                    safe_key, safe_value = self.environment._sanitize_env_var(key, value)
                    exec_commands.append(f"export {safe_key}='{safe_value}'")
            
            # 设置资源限制
            resource_limits = [
                f"ulimit -t {self.environment.config.max_execution_time}",  # CPU时间限制
                f"ulimit -v {self.environment.config.max_memory_mb * 1024}",  # 虚拟内存限制
                "ulimit -f 100000",  # 文件大小限制 (100MB)
                "ulimit -n 1024"     # 文件描述符限制
            ]
            exec_commands.extend(resource_limits)
            
            # 根据运行时准备代码执行
            if runtime in ["python3", "python"]:
                # Python代码执行
                code_file = f"task_{self.task_hash}.py"
                try:
                    encoded_code = base64.b64encode(code.encode('utf-8')).decode('ascii')
                    exec_commands.extend([
                        f"echo '{encoded_code}' | base64 -d > {code_file}",
                        f"timeout {self.environment.config.max_execution_time} {runtime} {code_file}"
                    ])
                except Exception as e:
                    raise ValueError(f"Failed to encode Python code: {e}")
            elif runtime == "node":
                # Node.js代码执行
                code_file = f"task_{self.task_hash}.js"
                try:
                    encoded_code = base64.b64encode(code.encode('utf-8')).decode('ascii')
                    exec_commands.extend([
                        f"echo '{encoded_code}' | base64 -d > {code_file}",
                        f"timeout {self.environment.config.max_execution_time} node {code_file}"
                    ])
                except Exception as e:
                    raise ValueError(f"Failed to encode Node.js code: {e}")
            elif runtime in ["bash", "sh"]:
                # Shell脚本执行
                try:
                    encoded_code = base64.b64encode(code.encode('utf-8')).decode('ascii')
                    exec_commands.extend([
                        f"echo '{encoded_code}' | base64 -d | {runtime}"
                    ])
                except Exception as e:
                    raise ValueError(f"Failed to encode shell code: {e}")
            
            # 列出执行后的文件
            exec_commands.append("echo '--- FILES_CREATED ---'")
            exec_commands.append("ls -la")
            
            # 执行命令
            full_command = " && ".join(exec_commands)
            result = self.environment._execute_remote_command(full_command, working_dir)
            
            # 解析结果
            stdout = result['stdout']
            stderr = result['stderr']
            
            # 提取创建的文件列表
            files_created = []
            if '--- FILES_CREATED ---' in stdout:
                files_section = stdout.split('--- FILES_CREATED ---')[-1]
                files_created = self.environment._parse_file_list(files_section)
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result['status'] == 'Success' and result['return_code'] == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result['return_code'],
                execution_time=execution_time,
                working_directory=working_dir,
                files_created=files_created,
                task_hash=self.task_hash,
                error_message=stderr if stderr else None
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"Code execution failed: {e}")
            
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=1,
                execution_time=execution_time,
                working_directory="",
                files_created=[],
                task_hash=self.task_hash,
                error_message=str(e)
            )
    
    def get_task_files(self, filename: Optional[str] = None) -> Dict[str, str]:
        """获取当前任务目录中的文件内容"""
        if not self.task_hash:
            logger.warning("No task executed yet, cannot get files")
            return {}
            
        return self.environment._get_task_files_by_hash(self.task_hash, filename)
