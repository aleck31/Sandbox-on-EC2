#!/usr/bin/env python3
"""
EC2 Sandbox 实例管理
基于EC2实例的代码执行沙盒实例管理
"""

import time
import base64
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, asdict
from .core import EC2SandboxEnv
from .utils import logger, generate_task_hash, sanitize_env_var, parse_file_list


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


class SandboxInstance:
    """沙盒实例 - 每个任务一个，负责具体的代码执行和文件管理"""
    
    def __init__(self, environment: 'EC2SandboxEnv', task_id: Optional[str] = None):
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
        allowed_runtimes = self.environment.config.allowed_runtimes or []
        if runtime not in allowed_runtimes:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=f"Runtime '{runtime}' not allowed. Allowed: {allowed_runtimes}",
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
            self.task_hash = generate_task_hash(task_data)
            
            # 创建文件系统
            working_dir = ""
            if create_filesystem:
                working_dir = self.environment._create_task_filesystem(self.task_hash, files)
            
            # 准备执行命令
            exec_commands = []
            
            # 设置环境变量
            if env_vars:
                for key, value in env_vars.items():
                    safe_key, safe_value = sanitize_env_var(key, value)
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
                files_created = parse_file_list(files_section)
            
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
