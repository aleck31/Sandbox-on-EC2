#!/usr/bin/env python3
"""
Strands Agent 工具集成
为EC2 Sandbox提供Strands Agent工具接口
"""

import json
import logging
from typing import Optional, Dict
from dataclasses import asdict
from strands import tool
from ec2_sandbox.core import EC2SandboxEnv, SandboxConfig
from ec2_sandbox.sandbox import ExecutionResult


logger = logging.getLogger(__name__)


def create_strands_tools(config: SandboxConfig):
    """创建Strands Agent工具"""

    # 创建沙盒环境（单例）
    sandbox_env = EC2SandboxEnv(config)
    
    @tool
    def code_execution_tool(
        code: str,
        runtime: str = "python3",
        task_id: Optional[str] = None,
        files: Optional[Dict[str, str]] = None,
        env_vars: Optional[Dict[str, str]] = None,
        create_filesystem: bool = True
    ) -> str:
        """
        在EC2沙箱中执行代码
        
        Args:
            code: 要执行的代码
            runtime: 运行时环境 (python3, python, node, bash, sh)
            task_id: 任务ID，用于标识任务
            files: 需要创建的文件 {filename: content}
            env_vars: 环境变量 {key: value}
            create_filesystem: 是否创建独立的文件系统
            
        Returns:
            执行结果的JSON字符串
        """
        try:
            # 创建沙盒实例
            sandbox_instance = sandbox_env.create_sandbox_instance(task_id)
            
            result = sandbox_instance.execute_code(
                code=code,
                runtime=runtime,
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
    def get_files_tool(task_hash: str, filename: Optional[str] = None) -> str:
        """
        获取任务目录中的文件内容
        
        Args:
            task_hash: 任务hash值
            filename: 特定文件名，不指定则获取所有文件
            
        Returns:
            文件内容的JSON字符串
        """
        try:
            files = sandbox_env._get_task_files_by_hash(task_hash, filename)
            return json.dumps(files, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    @tool
    def cleanup_tasks_tool(hours: Optional[int] = None) -> str:
        """
        清理过期的任务目录
        
        Args:
            hours: 清理多少小时前的任务，默认使用配置值
            
        Returns:
            清理结果
        """
        try:
            sandbox_env.cleanup_old_tasks(hours)
            return "清理完成"
        except Exception as e:
            return f"清理失败: {str(e)}"
    
    @tool
    def sandbox_env_status() -> str:
        """
        检查Sandbox底层环境(EC2实例)状态
        
        Returns:
            实例状态信息的JSON字符串
        """
        try:
            status = sandbox_env.check_instance_status()
            return json.dumps(status, indent=2, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    return [code_execution_tool, get_files_tool, cleanup_tasks_tool, sandbox_env_status]


# 便捷函数：从配置文件创建工具
def create_strands_tools_from_config(config_file: str = "config.json", environment: str = "default"):
    """
    从配置文件创建Strands工具
    
    Args:
        config_file: 配置文件路径
        environment: 环境名称
        
    Returns:
        Strands工具列表
    """
    try:
        from config_manager import ConfigManager
        
        manager = ConfigManager(config_file)
        config = manager.get_config(environment)
        
        return create_strands_tools(config)
        
    except Exception as e:
        logger.error(f"Failed to create tools from config: {e}")
        raise


if __name__ == "__main__":
    # 示例：从配置文件创建工具
    try:
        tools = create_strands_tools_from_config()
        print(f"Created {len(tools)} Strands tools:")
        for i, tool in enumerate(tools, 1):
            print(f"  {i}. {tool.__name__}")
            
        # 测试工具调用
        code_execution_tool = tools[0]
        result = code_execution_tool(
            code="print('Hello from Strands integration!')\nprint(f'123 x 456 = {123 x 456}')",
            runtime="python3",
            task_id="strands_test"
        )
        
        print("\nTest execution result:")
        print(result)
        
    except Exception as e:
        print(f"Error: {e}")
        print("Make sure config.json exists and Strands is installed (optional)")
