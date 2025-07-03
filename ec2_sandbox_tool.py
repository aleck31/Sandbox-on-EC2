#!/usr/bin/env python3
"""
EC2 Sandbox for Strands Agents
基于EC2实例的代码执行沙箱工具
"""

import os
import json
import hashlib
import subprocess
import tempfile
import shutil
import time
import logging
from datetime import datetime, timedelta
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


class EC2SandboxTool:
    """EC2沙箱工具类"""
    
    def __init__(self, config: SandboxConfig):
        self.config = config
        self.ec2_client = self._create_ec2_client()
        self.ssm_client = self._create_ssm_client()
        self._ensure_base_directory()
        
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
            import base64
            for filename, content in files.items():
                # 安全的文件名检查
                if not self._is_safe_filename(filename):
                    raise ValueError(f"Unsafe filename: {filename}")
                
                # 使用base64编码来避免特殊字符问题
                encoded_content = base64.b64encode(content.encode()).decode()
                commands.append(f"echo '{encoded_content}' | base64 -d > '{filename}'")
        
        # 执行命令
        full_command = " && ".join(commands)
        self._execute_remote_command(full_command)
        
        return task_dir
    
    def _is_safe_filename(self, filename: str) -> bool:
        """检查文件名是否安全"""
        dangerous_chars = ["../", "..\\", "/", "\\", "|", "&", ";", "$", "`"]
        return not any(char in filename for char in dangerous_chars)
    
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
                    'commands': [command]  # 注意：这里应该是列表格式
                },
                TimeoutSeconds=self.config.max_execution_time
            )
            
            command_id = response['Command']['CommandId']
            
            # 等待命令执行完成
            waiter = self.ssm_client.get_waiter('command_executed')
            waiter.wait(
                CommandId=command_id,
                InstanceId=self.config.instance_id,
                WaiterConfig={
                    'Delay': 2,
                    'MaxAttempts': 30  # 最多等待60秒 (2秒 * 30次)
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
    
    def execute_code(
        self,
        code: str,
        runtime: str = "python3",
        session_id: Optional[str] = None,
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        create_filesystem: bool = True
    ) -> ExecutionResult:
        """执行代码"""
        start_time = time.time()
        
        # 验证运行时
        if runtime not in self.config.allowed_runtimes:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Runtime '{runtime}' not allowed. Allowed: {self.config.allowed_runtimes}",
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
                "session_id": session_id or "default"
            }
            task_hash = self._generate_task_hash(task_data)
            
            # 创建文件系统
            working_dir = ""
            if create_filesystem:
                working_dir = self._create_task_filesystem(task_hash, files)
            
            # 准备执行命令
            exec_commands = []
            
            # 设置环境变量
            if env_vars:
                for key, value in env_vars.items():
                    exec_commands.append(f"export {key}='{value}'")
            
            # 设置资源限制
            resource_limits = [
                f"ulimit -t {self.config.max_execution_time}",  # CPU时间限制
                f"ulimit -v {self.config.max_memory_mb * 1024}",  # 虚拟内存限制
                "ulimit -f 100000",  # 文件大小限制 (100MB)
                "ulimit -n 1024"     # 文件描述符限制
            ]
            exec_commands.extend(resource_limits)
            
            # 根据运行时准备代码执行
            if runtime in ["python3", "python"]:
                # Python代码执行
                code_file = f"task_{task_hash}.py"
                # 使用base64编码来避免引号和特殊字符问题
                import base64
                encoded_code = base64.b64encode(code.encode()).decode()
                exec_commands.extend([
                    f"echo '{encoded_code}' | base64 -d > {code_file}",
                    f"timeout {self.config.max_execution_time} {runtime} {code_file}"
                ])
            elif runtime == "node":
                # Node.js代码执行
                code_file = f"task_{task_hash}.js"
                import base64
                encoded_code = base64.b64encode(code.encode()).decode()
                exec_commands.extend([
                    f"echo '{encoded_code}' | base64 -d > {code_file}",
                    f"timeout {self.config.max_execution_time} node {code_file}"
                ])
            elif runtime in ["bash", "sh"]:
                # Shell脚本执行
                import base64
                encoded_code = base64.b64encode(code.encode()).decode()
                exec_commands.extend([
                    f"echo '{encoded_code}' | base64 -d | {runtime}"
                ])
            
            # 列出执行后的文件
            exec_commands.append("echo '--- FILES_CREATED ---'")
            exec_commands.append("ls -la")
            
            # 执行命令
            full_command = " && ".join(exec_commands)
            result = self._execute_remote_command(full_command, working_dir)
            
            # 解析结果
            stdout = result['stdout']
            stderr = result['stderr']
            
            # 提取创建的文件列表
            files_created = []
            if '--- FILES_CREATED ---' in stdout:
                files_section = stdout.split('--- FILES_CREATED ---')[-1]
                files_created = self._parse_file_list(files_section)
            
            execution_time = time.time() - start_time
            
            return ExecutionResult(
                success=result['status'] == 'Success' and result['return_code'] == 0,
                stdout=stdout,
                stderr=stderr,
                return_code=result['return_code'],
                execution_time=execution_time,
                working_directory=working_dir,
                files_created=files_created,
                task_hash=task_hash,
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
                task_hash=task_hash,
                error_message=str(e)
            )
    
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
    
    def cleanup_old_tasks(self, hours: Optional[int] = None):
        """清理过期的任务目录"""
        cleanup_hours = hours or self.config.cleanup_after_hours
        
        try:
            # 查找并删除过期目录
            command = f"""
            find {self.config.base_sandbox_dir} -type d -name "*" -mtime +{cleanup_hours/24:.1f} -exec rm -rf {{}} + 2>/dev/null || true
            """
            
            result = self._execute_remote_command(command)
            logger.info(f"Cleanup completed: {result}")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_task_files(self, task_hash: str, filename: Optional[str] = None) -> Dict[str, str]:
        """获取任务目录中的文件内容"""
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


def create_strands_tool(config: SandboxConfig):
    """创建Strands Agent工具"""
    from strands.tools import tool
    
    sandbox = EC2SandboxTool(config)
    
    @tool
    def ec2_code_execution(
        code: str,
        runtime: str = "python3",
        session_id: Optional[str] = None,
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        create_filesystem: bool = True
    ) -> str:
        """
        在EC2沙箱中执行代码
        
        Args:
            code: 要执行的代码
            runtime: 运行时环境 (python3, python, node, bash, sh)
            session_id: 会话ID，用于任务分组
            files: 需要创建的文件 {filename: content}
            env_vars: 环境变量 {key: value}
            create_filesystem: 是否创建独立的文件系统
            
        Returns:
            执行结果的JSON字符串
        """
        try:
            result = sandbox.execute_code(
                code=code,
                runtime=runtime,
                session_id=session_id,
                files=files,
                env_vars=env_vars,
                create_filesystem=create_filesystem
            )
            
            return json.dumps(asdict(result), indent=2, ensure_ascii=False)
            
        except Exception as e:
            error_result = ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=1,
                execution_time=0,
                working_directory="",
                files_created=[],
                error_message=str(e)
            )
            return json.dumps(asdict(error_result), indent=2, ensure_ascii=False)
    
    @tool
    def ec2_get_files(task_hash: str, filename: Optional[str] = None) -> str:
        """
        获取任务目录中的文件内容
        
        Args:
            task_hash: 任务hash值
            filename: 特定文件名，不指定则获取所有文件
            
        Returns:
            文件内容的JSON字符串
        """
        try:
            files = sandbox.get_task_files(task_hash, filename)
            return json.dumps(files, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    @tool
    def ec2_cleanup_tasks(hours: Optional[int] = None) -> str:
        """
        清理过期的任务目录
        
        Args:
            hours: 清理多少小时前的任务，默认使用配置值
            
        Returns:
            清理结果
        """
        try:
            sandbox.cleanup_old_tasks(hours)
            return "清理完成"
        except Exception as e:
            return f"清理失败: {str(e)}"
    
    @tool
    def ec2_instance_status() -> str:
        """
        检查EC2实例状态
        
        Returns:
            实例状态信息的JSON字符串
        """
        try:
            status = sandbox.check_instance_status()
            return json.dumps(status, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    return [ec2_code_execution, ec2_get_files, ec2_cleanup_tasks, ec2_instance_status]


if __name__ == "__main__":
    # 示例配置
    config = SandboxConfig(
        instance_id="i-1234567890abcdef0",  # 替换为实际的实例ID
        region="us-east-1",
        aws_profile="default",  # 或使用access_key_id/secret_access_key
        base_sandbox_dir="/tmp/sandbox",
        max_execution_time=300,
        max_memory_mb=1024,
        cleanup_after_hours=24
    )
    
    # 创建沙箱工具
    sandbox = EC2SandboxTool(config)
    
    # 测试代码执行
    test_code = """
import os
import sys
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Environment variables: {len(os.environ)}")

# 创建一个测试文件
with open('test_output.txt', 'w') as f:
    f.write('Hello from EC2 Sandbox!')

print("Test completed successfully!")
"""
    
    result = sandbox.execute_code(
        code=test_code,
        runtime="python3",
        session_id="test_session",
        create_filesystem=True
    )
    
    print("Execution Result:")
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
