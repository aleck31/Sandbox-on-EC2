#!/usr/bin/env python3
"""
EC2 Sandbox Agent - Gradio Demo
基于 Gradio 的 Agent 演示界面，展示 EC2 沙盒代码执行能力
"""

import gradio as gr
from gradio import ChatMessage
import json
import time
from typing import List, Dict, Any, Generator
import logging

from strands import Agent
from strands.models.bedrock import BedrockModel
from config_manager import ConfigManager
from strands_tools import create_strands_tools

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EC2SandboxDemo:
    """EC2 Sandbox Agent Demo 类"""
    
    def __init__(self):
        """初始化 Demo"""
        self.setup_agent()
        
    def setup_agent(self):
        """设置 Agent"""
        try:
            # 加载配置
            config_manager = ConfigManager('config.json')
            config = config_manager.get_config('default')
            
            # 创建工具
            tools = create_strands_tools(config)
            
            # 创建 Bedrock 模型
            bedrock_model = BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                region_name="us-west-2",
                temperature=0.1,
                max_tokens=4000
            )
            
            # 创建 Agent
            self.agent = Agent(
                model=bedrock_model,
                system_prompt="""你是一个专业的代码执行助手，运行在安全的EC2沙盒环境中。

🚀 **你的能力：**
- 在隔离的EC2环境中安全执行代码
- 支持Python、Node.js、Bash、Shell多种运行时
- 预装完整的数据分析库：pandas, numpy, matplotlib, plotly, scipy等
- 自动文件管理和结果展示

💡 **最佳实践：**
- 编写清晰、简洁的代码
- 优先使用预装的数据分析库
- 遇到错误时分析并修正代码
- 为复杂任务提供分步骤解决方案

🔧 **可用工具：**
- execute_code_in_sandbox: 执行代码（支持python3, node, bash, sh）
- get_task_files: 获取生成的文件
- check_sandbox_status: 检查环境状态

请始终以友好、专业的方式协助用户完成编程和数据分析任务。""",
                tools=tools
            )
            
            logger.info("Agent 初始化成功")
            
        except Exception as e:
            logger.error(f"Agent 初始化失败: {e}")
            self.agent = None
    
    def chat_with_agent(self, message: str, history: List[Dict]) -> Generator[ChatMessage, None, None]:
        """与 Agent 聊天的生成器函数"""
        
        if not self.agent:
            yield ChatMessage(
                role="assistant",
                content="❌ Agent 未正确初始化，请检查配置。",
                metadata={"title": "🚨 系统错误"}
            )
            return
        
        # 显示思考状态
        thinking_msg = ChatMessage(
            role="assistant",
            content="正在分析您的请求...",
            metadata={
                "title": "🧠 思考中",
                "status": "pending"
            }
        )
        yield thinking_msg
        
        try:
            # 调用 Agent
            start_time = time.time()
            response = self.agent(message)
            duration = time.time() - start_time
            
            # 更新思考状态为完成
            thinking_msg.metadata = {
                "title": "🧠 分析完成",
                "status": "done",
                "duration": duration
            }
            yield thinking_msg
            
            # 提取实际的响应内容
            if isinstance(response, dict):
                # 如果是字典格式，提取message内容
                if 'message' in response and 'content' in response['message']:
                    content_list = response['message']['content']
                    if isinstance(content_list, list) and len(content_list) > 0:
                        actual_content = content_list[0].get('text', str(response))
                    else:
                        actual_content = str(response)
                else:
                    actual_content = str(response)
            else:
                # 如果是字符串，直接使用
                actual_content = str(response)
            
            # 显示 Agent 响应
            yield ChatMessage(
                role="assistant",
                content=actual_content,
                metadata={
                    "title": "✅ 执行完成",
                    "duration": duration
                }
            )
            
        except Exception as e:
            logger.error(f"Agent 调用失败: {e}")
            
            # 更新思考状态为错误
            thinking_msg.metadata = {
                "title": "❌ 执行失败",
                "status": "done"
            }
            yield thinking_msg
            
            # 显示错误信息
            yield ChatMessage(
                role="assistant",
                content=f"抱歉，执行过程中遇到错误：\n\n```\n{str(e)}\n```\n\n请尝试重新描述您的需求，或者检查网络连接。",
                metadata={"title": "🚨 错误详情"}
            )

def create_demo():
    """创建 Gradio Demo"""
    
    # 初始化 Demo 类
    demo_instance = EC2SandboxDemo()
    
    # 创建聊天界面
    demo = gr.ChatInterface(
        fn=demo_instance.chat_with_agent,
        type="messages",
        title="🚀 EC2 Sandbox Agent Demo",
        description="""
        **欢迎使用 EC2 沙盒代码执行助手！**
        
        这是一个运行在 AWS EC2 实例上的代码执行环境，支持：
        - 🐍 **Python** (pandas, numpy, matplotlib, plotly, scipy等)
        - 🟢 **Node.js** (JavaScript运行时)
        - 🐚 **Bash/Shell** (系统脚本)
        - 📊 **数据分析** (完整的数据科学工具栈)
        - 📁 **文件管理** (自动文件创建和管理)
        """,
        examples=[
            "用Python创建一个简单的数据分析脚本，分析销售数据并生成报告",
            "写一个Node.js程序计算前20个斐波那契数",
            "用matplotlib创建一个包含多个子图的数据可视化",
            "创建一个Bash脚本来统计当前目录的文件信息",
            "用pandas处理CSV数据并生成统计摘要"
        ],
        # theme=gr.themes.Soft(),
        css="""
        .gradio-container {
            max-width: 1200px !important;
        }
        .chat-message {
            font-size: 14px;
        }
        """
    )
    
    return demo

def main():
    """主函数"""
    print("🚀 启动 EC2 Sandbox Agent Demo...")
    
    # 创建并启动 Demo
    demo = create_demo()
    
    # 启动服务
    demo.launch(
        server_name="0.0.0.0",  # 允许外部访问
        server_port=7860,       # 默认端口
        share=False,            # 不创建公共链接
        debug=True,             # 启用调试模式
        show_error=True         # 显示错误信息
    )

if __name__ == "__main__":
    main()
