#!/usr/bin/env python3
"""
Strands Agent 工具集成
为EC2 Sandbox提供Strands Agent工具接口
"""

import json
import os
import time
from typing import Optional, Dict, List, Any, Callable
from dataclasses import asdict
from strands import tool
from ec2_sandbox.core import EC2SandboxEnv, SandboxConfig
from ec2_sandbox.sandbox import ExecutionResult
from ec2_sandbox.session_manager import SessionContext, create_session_context
from ec2_sandbox.tool_response import ToolResponse
from ec2_sandbox.utils import get_logger

logger = get_logger(__name__)

# 全局变量存储当前会话上下文
_current_context: Optional[SessionContext] = None

def set_session_context(context: SessionContext):
    """设置当前会话上下文"""
    global _current_context
    _current_context = context

def get_session_context() -> Optional[SessionContext]:
    """获取当前会话上下文"""
    return _current_context

def create_strands_tools(config: SandboxConfig, session_id: str) -> List[Callable[..., str]]:
    """创建 Strands 沙盒工具"""

    # 创建沙盒环境（单例）
    sandbox_env = EC2SandboxEnv(config)
    
    # 创建会话上下文
    context = create_session_context(session_id, config.base_sandbox_dir)
    set_session_context(context)
    
    logger.info(f"创建沙盒工具 - {context.session_id}")
    
    @tool
    def execute_code_in_sandbox(
        code: str,
        runtime: str = "python",
        task_id: Optional[str] = None,
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        create_filesystem: bool = True
    ) -> str:
        """
        在EC2沙箱中安全执行代码(最大代码长度: 70KB)
        
        注意: 如果使用GPU沙盒环境, python运行时自动支持GPU加速库(PyTorch, CuDF等)
        
        Args:
            code: 要执行的代码 (必需)
            runtime: 运行时环境，可选值: "python"(默认), "node", "bash", "sh"
            task_id: 任务ID, 用于标识任务
            files: 需要创建的文件 {filename: content}
            env_vars: 可选的环境变量 {key: value}
            create_filesystem: 是否创建独立文件系统 (默认: True)
            
        Returns:
            执行结果的JSON字符串(包含工作目录路径和创建的文件列表)
        """
        try:
            # 检查代码长度
            code_size = len(code.encode('utf-8'))
            # 设置安全限制为70KB，为各种情况留出余量
            MAX_CODE_SIZE = 71680
            
            if code_size > MAX_CODE_SIZE:
                error_result = ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"代码过长 ({code_size:,} 字节 = {code_size/1024:.1f}KB)，超过安全限制。\n\n"
                           f"📏 限制详情：\n"
                           f"• AWS SSM实际限制：~99KB（总命令大小）\n"
                           f"• 最大代码限制：~72KB（实测边界）\n"
                           f"• 安全代码限制：70KB（推荐使用）\n"
                           f"• 当前代码大小：{code_size/1024:.1f}KB\n\n"
                           f"🔧 代码优化建议：\n"
                           f"1. 移除不必要的注释、空行和调试代码\n"
                           f"2. 使用更简洁的变量名和函数名\n"
                           f"3. 将复杂逻辑拆分为多个简单函数\n"
                           f"4. 避免重复代码，使用循环和函数复用\n"
                           f"5. 移除不必要的导入和依赖\n"
                           f"6. 考虑将大任务分解为多个小步骤执行\n"
                           f"7. 将大量数据改用文件输入而非硬编码",
                    return_code=1,
                    execution_time=0,
                    session_id='',
                    working_directory="",
                    files_created=[],
                    task_hash=None,
                    error_message=f"Code too long: {code_size} bytes ({code_size/1024:.1f}KB) exceeds {MAX_CODE_SIZE} bytes (70KB) safe limit"
                )
                return json.dumps(asdict(error_result), indent=2, ensure_ascii=False)

            # 获取当前会话上下文
            ctx = get_session_context()
            if not ctx:
                return json.dumps({
                    "success": False,
                    "error": "会话上下文未初始化"
                }, ensure_ascii=False)

            # 创建沙盒实例
            sandbox = sandbox_env.create_sandbox_instance(
                task_id or f"task_{int(time.time())}"
            )
            
            # 临时修改沙盒环境的基础目录为会话目录
            original_base_dir = sandbox_env.config.base_sandbox_dir
            sandbox_env.config.base_sandbox_dir = ctx.session_path
            
            try:
                # 执行代码
                result = sandbox.execute_code(
                    code=code,
                    runtime=runtime,
                    files=files,
                    env_vars=env_vars,
                    create_filesystem=create_filesystem
                )
                
                # 修正工作目录路径显示
                if result.working_directory:
                    result.working_directory = f"{ctx.session_path}/{result.task_hash}"
                
                # 更新会话活动
                ctx.session_data.update_activity()
                
            finally:
                # 恢复原始基础目录
                sandbox_env.config.base_sandbox_dir = original_base_dir
            
            # 构建返回结果，包含会话信息
            response_data = ExecutionResult(
                success=result.success,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.return_code,
                execution_time=result.execution_time,
                task_hash=result.task_hash,
                error_message=result.stderr or "执行失败" if not result.success else None,
                working_directory=result.working_directory,
                files_created=result.files_created,
                # 添加会话信息
                session_id=ctx.session_id,
                task_count=ctx.session_data.task_count,
            )
            
            return response_data.to_json()
            
        except Exception as e:
            logger.error(f"代码执行失败: {e}")
            ctx = get_session_context()
            error_result = ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                return_code=1,
                execution_time=0,
                working_directory="",
                files_created=[],
                error_message=str(e),
                session_id=ctx.session_id if ctx else None
            )
            return error_result.to_json()
    
    @tool
    def get_session_files(
        filename: Optional[str] = None,
        task_hash: Optional[str] = None
    ) -> str:
        """
        获取当前用户会话中的文件内容 - 支持精确查找, 支持跨任务文件访问
        
        Args:
            filename: 文件名 (可选)
            task_hash: 任务哈希 (可选)
            
        注意: filename 和 task_hash 至少需要提供一个参数
        
        Returns:
            统一格式的JSON, 包含文件内容
            
        示例用法：
        - get_session_files(task_hash="abc123") # 获取指定任务的所有文件内容
        - get_session_files(filename="data.csv") # 在当前会话中查找并获取特定文件内容
        - get_session_files(filename="data.csv", task_hash="abc123") # 在指定任务中获取特定文件内容
        - 在代码中使用相对路径，如: open("../task_hash/file.txt") # 访问其他任务的文件
        """
        try:
            ctx = get_session_context()
            if not ctx:
                return ToolResponse.create_error(
                    error_message="会话上下文未初始化"
                ).to_json()
            
            # 参数验证：至少需要提供一个参数
            if not filename and not task_hash:
                return ToolResponse.create_error(
                    error_message="请提供 filename 或 task_hash 参数。如需查看会话结构，请使用 list_session_structure 工具。",
                    session_id=ctx.session_id
                ).to_json()
            
            session_path = ctx.session_path
            
            # 统一的文件读取函数
            def read_file_content(file_path: str) -> str:
                read_command = f"cat '{file_path}'"
                read_result = sandbox_env._execute_remote_command(read_command)
                if read_result.get('return_code') == 0:
                    return read_result.get('stdout', '')
                else:
                    return f"<读取失败: {read_result.get('stderr', 'Unknown error')}>"
            
            if filename:
                # 查找特定文件
                if task_hash:
                    # 在指定任务中查找
                    find_command = f"find {session_path}/{task_hash} -name '{filename}' -type f -maxdepth 1 2>/dev/null"
                else:
                    # 在整个会话目录中查找
                    find_command = f"find {session_path} -name '{filename}' -type f 2>/dev/null"
                
                find_result = sandbox_env._execute_remote_command(find_command)
                
                if find_result.get('return_code') == 0 and find_result.get('stdout', '').strip():
                    file_path = find_result['stdout'].strip().split('\n')[0]  # 取第一个匹配的文件
                    content = read_file_content(file_path)
                    
                    # 提取任务哈希
                    found_task = os.path.basename(os.path.dirname(file_path))
                    
                    return ToolResponse.create_success(
                        data={
                            "filename": filename,
                            "content": content,
                            "found_in_task": found_task,
                            "full_path": file_path
                        },
                        message=f"成功获取文件: {filename}",
                        session_id=ctx.session_id
                    ).to_json()
                else:
                    search_scope = f"任务 {task_hash}" if task_hash else "所有任务"
                    return ToolResponse.create_error(
                        error_message=f"文件未找到: {filename} (搜索范围: {search_scope})",
                        session_id=ctx.session_id
                    ).to_json()
            
            else:
                # 获取指定任务的所有文件内容 (task_hash 必须存在)
                task_dir_path = f"{session_path}/{task_hash}"
                
                # 检查任务目录是否存在
                check_command = f"test -d '{task_dir_path}' && echo 'exists'"
                check_result = sandbox_env._execute_remote_command(check_command)
                
                if check_result.get('return_code') != 0 or 'exists' not in check_result.get('stdout', ''):
                    return ToolResponse.create_error(
                        error_message=f"任务目录不存在: {task_hash}",
                        session_id=ctx.session_id,
                        data={"task_hash": task_hash}
                    ).to_json()
                
                # 列出指定任务目录中的所有文件
                list_files_command = f"find {task_dir_path} -maxdepth 1 -type f 2>/dev/null"
                files_result = sandbox_env._execute_remote_command(list_files_command)
                
                task_files = {}
                if files_result.get('return_code') == 0 and files_result.get('stdout', '').strip():
                    file_paths = files_result['stdout'].strip().split('\n')
                    
                    for file_path in file_paths:
                        file_name = os.path.basename(file_path)
                        task_files[file_name] = read_file_content(file_path)
                
                return ToolResponse.create_success(
                    data={
                        "task_hash": task_hash,
                        "files": task_files,
                        "total_files": len(task_files)
                    },
                    message=f"成功获取任务 {task_hash} 的 {len(task_files)} 个文件",
                    session_id=ctx.session_id
                ).to_json()
                
        except Exception as e:
            logger.error(f"获取文件失败: {e}")
            ctx = get_session_context()
            return ToolResponse.create_error(
                error_message=f"获取文件失败: {str(e)}",
                session_id=ctx.session_id if ctx else None
            ).to_json()
    
    @tool
    def cleanup_expired_tasks(hours: Optional[int] = None) -> str:
        """
        清理过期的任务目录
        
        Args:
            hours: 清理多少小时前的任务，默认使用配置值
            
        Returns:
            统一格式的JSON字符串
        """
        try:
            sandbox_env.cleanup_old_tasks(hours)
            ctx = get_session_context()
            
            return ToolResponse.create_success(
                data={"hours": hours or "默认配置值"},
                message="任务清理完成",
                session_id=ctx.session_id if ctx else None
            ).to_json()
        except Exception as e:
            ctx = get_session_context()
            return ToolResponse.create_error(
                error_message=f"清理失败: {str(e)}",
                session_id=ctx.session_id if ctx else None
            ).to_json()
    
    @tool
    def check_sandbox_status() -> str:
        """
        检查Sandbox底层环境(EC2实例)状态
        
        Returns:
            统一格式的JSON字符串
        """
        try:
            status = sandbox_env.check_instance_status()
            
            # 添加会话信息
            ctx = get_session_context()
            if ctx:
                status.update({
                    "session_tasks": ctx.list_session_tasks(),
                    "task_count": ctx.session_data.task_count
                })
            
            return ToolResponse.create_success(
                data=status,
                message="沙盒状态检查完成",
                session_id=ctx.session_id if ctx else None
            ).to_json()
        except Exception as e:
            ctx = get_session_context()
            return ToolResponse.create_error(
                error_message=f"状态检查失败: {str(e)}",
                session_id=ctx.session_id if ctx else None
            ).to_json()
    
    @tool
    def list_session_structure() -> str:
        """
        列出当前会话的文件结构
        
        Returns:
            统一格式的JSON字符串
        """
        try:
            ctx = get_session_context()
            if not ctx:
                return ToolResponse.create_error(
                    error_message="会话上下文未初始化"
                ).to_json()
            
            session_structure = {
                "session_path": ctx.session_path,
                "task_count": ctx.session_data.task_count,
                "tasks": {}
            }
            
            # 使用 EC2 远程命令列出会话目录下的所有任务目录
            list_dirs_command = f"find {ctx.session_path} -maxdepth 1 -type d ! -path {ctx.session_path} 2>/dev/null"
            dirs_result = sandbox_env._execute_remote_command(list_dirs_command)
            
            if dirs_result.get('return_code') == 0 and dirs_result.get('stdout', '').strip():
                task_dirs = dirs_result['stdout'].strip().split('\n')
                
                for task_dir_path in task_dirs:
                    task_name = os.path.basename(task_dir_path)
                    task_info = {
                        "path": task_dir_path,
                        "files": []
                    }
                    
                    # 列出任务目录中的文件信息
                    list_files_command = f"ls -la {task_dir_path} 2>/dev/null"
                    files_result = sandbox_env._execute_remote_command(list_files_command)
                    
                    if files_result.get('return_code') == 0:
                        files_output = files_result.get('stdout', '')
                        # 解析 ls -la 输出
                        for line in files_output.split('\n'):
                            if line.strip() and not line.startswith('total') and not line.startswith('d'):
                                parts = line.split()
                                if len(parts) >= 9:
                                    filename = ' '.join(parts[8:])  # 文件名可能包含空格
                                    if filename not in ['.', '..']:
                                        task_info["files"].append({
                                            "name": filename,
                                            "permissions": parts[0],
                                            "size": parts[4],
                                            "modified": ' '.join(parts[5:8])
                                        })
                    
                    session_structure["tasks"][task_name] = task_info
            
            return ToolResponse.create_success(
                data=session_structure,
                message=f"成功获取会话结构，包含 {len(session_structure['tasks'])} 个任务",
                session_id=ctx.session_id
            ).to_json()
            
        except Exception as e:
            ctx = get_session_context()
            return ToolResponse.create_error(
                error_message=f"获取会话结构失败: {str(e)}",
                session_id=ctx.session_id if ctx else None
            ).to_json()
    
    # 返回工具列表
    tools_list = [
        execute_code_in_sandbox,
        get_session_files,
        list_session_structure,
        cleanup_expired_tasks,
        check_sandbox_status
    ]
    
    return tools_list
