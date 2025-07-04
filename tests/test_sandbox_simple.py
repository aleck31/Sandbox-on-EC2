#!/usr/bin/env python3
"""
简单测试: 验证EC2沙盒基础功能
"""

import json
import os
import sys
from dataclasses import dataclass, asdict

# 添加父目录到路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv, SandboxConfig


def load_test_config():
    """从配置文件动态加载测试配置"""
    try:
        # 查找配置文件
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        
        # 使用配置管理器加载配置
        manager = ConfigManager(config_path)
        config = manager.get_config('default')  # 使用正确的环境名称
        
        # 调整测试参数（保持原有配置，只调整测试相关的）
        original_execution_time = config.max_execution_time
        config.max_execution_time = min(60, original_execution_time)  # 测试用较短时间，但不超过原配置
        
        print(f"从配置文件加载配置成功:")
        print(f"  实例ID: {config.instance_id}")
        print(f"  区域: {config.region}")
        print(f"  AWS配置文件: {config.aws_profile}")
        print(f"  沙盒目录: {config.base_sandbox_dir}")
        print(f"  测试执行时间限制: {config.max_execution_time}s")
        
        return config
        
    except Exception as e:
        print(f"加载配置失败: {e}")
        print("请确保已运行 create_ec2_sandbox.sh 创建配置文件")
        sys.exit(1)


if __name__ == "__main__":
    # 示例配置
    config = load_test_config()
    
    # 创建沙盒环境（单例）
    sandbox_env = EC2SandboxEnv(config)
    
    # 创建沙盒实例执行代码
    sandbox_instance = sandbox_env.create_sandbox_instance("my_task")
    
    test_code = """
import os
import sys
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

# 创建一个测试文件
with open('test_output.txt', 'w') as f:
    f.write('Hello from Sandbox Instance!')

print("Test completed successfully!")
"""
    
    result = sandbox_instance.execute_code(
        code=test_code,
        runtime="python3",
        create_filesystem=True
    )
    
    print("Execution Result:")
    print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    
    # 获取任务文件
    files = sandbox_instance.get_task_files()
    print(f"\nGenerated files: {list(files.keys())}")
    
    # 检查环境状态
    status = sandbox_env.check_instance_status()
    print(f"\nInstance status: {status}")
