#!/usr/bin/env python3
"""
测试 MCP 集成是否正常工作
"""
import os
import sys
import asyncio
from strands import Agent
from strands.models.bedrock import BedrockModel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_manager import ConfigManager
from ec2_sandbox.strands_tools import create_strands_tools


async def test_mcp_integration():
    """测试 MCP 集成"""
    try:
        print("🔍 测试 MCP 集成...")
        
        # 加载配置
        config_manager = ConfigManager('config.json')
        config = config_manager.get_sandbox_config('sandbox-default')
        mcp_settings = config_manager.get_raw_config('mcp_settings')
        exa_api_key = mcp_settings.get('exa_api_key')
        
        if not exa_api_key:
            print("❌ 未找到 Exa API Key")
            return
        
        # 创建本地工具
        local_tools = create_strands_tools(config, 'sid-a1b2c3d4e5f')
        print(f"✅ 本地工具数量: {len(local_tools)}")
        
        # 创建 Bedrock 模型
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name="us-west-2",
            temperature=0.1,
            max_tokens=1000
        )
        
        # 创建 MCP 客户端
        from mcp import stdio_client, StdioServerParameters
        from strands.tools.mcp import MCPClient
        
        mcp_client = MCPClient(lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "exa-mcp-server"],
                env={"EXA_API_KEY": exa_api_key}
            )
        ))
        
        print("✅ MCP 客户端创建成功")
        
        # 在 MCP context 中测试
        with mcp_client:
            print("✅ MCP 连接建立成功")
            
            # 获取 MCP 工具
            mcp_tools = mcp_client.list_tools_sync()
            print(f"✅ MCP 工具数量: {len(mcp_tools)}")
            
            # 合并工具
            all_tools = local_tools + mcp_tools
            print(f"✅ 总工具数量: {len(all_tools)}")
            
            # 创建 Agent
            agent = Agent(
                model=bedrock_model,
                tools=all_tools,
                system_prompt="You are a helpful assistant with web search and code execution capabilities."
            )
            
            print("✅ Agent 创建成功")
            
            # 测试简单查询
            print("\n🧪 测试简单查询...")
            response = agent("Search for the latest Python version and tell me about it.")
            print(f"✅ 查询成功: {str(response)[:200]}...")
            
            return True
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mcp_integration())
    if success:
        print("\n🎉 MCP 集成测试成功！")
    else:
        print("\n❌ MCP 集成测试失败！")
