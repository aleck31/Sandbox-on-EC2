#!/usr/bin/env python3
"""
功能测试：验证 EC2Sandbox 工具与 Strands Agent 集成
"""

import os
from strands import Agent, tool
from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv

# 设置AWS凭证环境变量（Strands Agent需要）
os.environ['AWS_PROFILE'] = 'lab'
os.environ['AWS_DEFAULT_REGION'] = 'ap-northeast-1'

print("🔧 初始化EC2沙箱工具...")
config_manager = ConfigManager('config.json')
config = config_manager.get_config('default')
config.region = 'ap-northeast-1'
sandbox_env = EC2SandboxEnv(config)

@tool
def run_python_code(code: str) -> str:
    """
    在EC2沙箱中执行Python代码
    
    Args:
        code: 要执行的Python代码
    
    Returns:
        代码执行结果
    """
    print(f"🐍 执行代码: {code[:50]}...")
    
    sandbox = sandbox_env.create_sandbox_instance("agent_test")
    result = sandbox.execute_code(
        code=code,
        runtime="python3"
    )
    
    if result.success:
        return f"执行成功:\n{result.stdout}"
    else:
        return f"执行失败:\n{result.stderr}"

def main():
    print("🚀 简单测试：Strands Agent + EC2 Sandbox")
    print("="*50)
    
    try:
        # 创建Agent
        print("🤖 创建Agent...")
        agent = Agent(
            system_prompt="你是一个Python编程助手。当用户要求执行Python代码时，使用run_python_code工具。",
            tools=[run_python_code]
        )
        print("✅ Agent创建成功")
        
        # 简单测试
        print("\n📝 测试请求: 计算2+2")
        response = agent("请执行Python代码计算2+2并显示结果")
        print(f"\n🤖 Agent响应:\n{response}")
        
        # 停止定时器
        sandbox_env.stop_cleanup_timer()
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
