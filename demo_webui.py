#!/usr/bin/env python3
"""
EC2 Sandbox Agent - Gradio Demo (支持会话管理)
基于 Gradio UI 的 Agent 演示，展示 Strands Agents + EC2沙盒代码执行能力
"""

import gradio as gr
from gradio import ChatMessage
import json
import time
import asyncio
import re
from typing import List, Dict, Any, Generator, Optional
import logging
from strands import Agent
from strands.models.bedrock import BedrockModel
from config_manager import ConfigManager
from ec2_sandbox.core import SandboxConfig
from ec2_sandbox.session_manager import get_session_manager
from ec2_sandbox.strands_tools import create_strands_tools

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def extract_tool_results_from_messages(messages):
    """从消息历史中提取工具执行结果"""
    tool_results = []
    
    for msg in messages:
        if isinstance(msg, dict) and msg.get('role') == 'user':
            content = msg.get('content', [])
            for item in content:
                if isinstance(item, dict) and 'toolResult' in item:
                    tool_result = item['toolResult']
                    if tool_result.get('status') == 'success':
                        result_content = tool_result.get('content', [])
                        for result_item in result_content:
                            if isinstance(result_item, dict) and 'text' in result_item:
                                text = result_item['text']
                                try:
                                    json_match = re.search(r'\{.*\}', text, re.DOTALL)
                                    if json_match:
                                        data = json.loads(json_match.group())
                                        tool_results.append(data)
                                except Exception as e:
                                    logger.debug(f"JSON 解析失败: {e}")
    
    return tool_results

def format_file_info(tool_results, base_sandbox_dir):
    """格式化文件信息显示"""
    if not tool_results:
        return "暂无文件信息"
    
    info_lines = []
    first_chat = True
    
    for i, result in enumerate(tool_results):
        # 只在第一次显示会话信息
        if first_chat:
            session_id = result.get('session_id', 'N/A')
            if session_id != 'N/A':
                info_lines.append(f"**🔗 会话: {session_id}**")
                info_lines.append("")  # 空行
                first_chat = False
        
        # 任务信息
        info_lines.append(f"**📋 任务 {i+1}** ID: {result.get('task_hash', 'N/A')}")
        
        working_directory = result.get('working_directory', '')
        # 屏蔽敏感的工作目录路径
        masked_dir = working_directory.replace(base_sandbox_dir, '~', 1)
        info_lines.append(f"  - 📂 工作目录: `{masked_dir}`")
        
        files_created = result.get('files_created', [])
        if files_created:
            info_lines.append(f"  - 📄 创建的文件:")
            for filename in files_created:
                # 构建文件下载链接 - 拼接 API 接口路径
                if working_directory:
                    download_link = f"/file{working_directory}/{filename}"
                else:
                    download_link = f"/file/{filename}"
                info_lines.append(f"    - `{filename}` [📥]({download_link})")
        
        execution_time = result.get('execution_time')
        return_code = result.get('return_code')
        if return_code is not None:
            status = "✅ 成功" if return_code == 0 else "❌ 失败"
            if execution_time:
                info_lines.append(f"  - 📊 执行状态: {status} (⏱️ 用时{execution_time:.2f}秒)")
            else:
                info_lines.append(f"  - 📊 执行状态: {status}")
        
        info_lines.append("")  # 空行分隔任务
    
    return "\n".join(info_lines)

# 系统提示词
SYSTEM_PROMPT = """You are a professional code execution assistant running in a secure EC2 sandbox environment.

🚀 **Your Capabilities:**
- Execute code safely in an isolated EC2 environment
- Support multiple runtimes: Python, Node.js, Bash, Shell
- Pre-installed comprehensive data analysis libraries: pandas, numpy, matplotlib, plotly, scipy, etc.
- Automatic file management and result presentation
- 🔍 **Web Search**: Search for latest information, technical documentation, and code examples via Exa AI

💡 **Best Practices:**
- Write clear, concise code
- Prioritize pre-installed data analysis libraries
- Analyze and fix code when encountering errors
- Provide step-by-step solutions for complex tasks
- Use search functionality when latest information is needed

🔧 **Available Tools:**
- execute_code_in_sandbox: Execute code (supports python3, node, bash, sh)
- get_task_files: Retrieve generated files
- check_sandbox_status: Check environment status
- 🌐 Exa Search Tools: Search web content, technical docs, code examples

Please assist users with programming and data analysis tasks in a friendly, professional manner. When latest information or technical documentation is needed, proactively use search functionality."""

class EC2SandboxDemo:
    """EC2 Sandbox Agent Demo 类 - 支持会话管理"""
    
    def __init__(self):
        """初始化 Demo"""
        self.agent: Optional[Agent] = None
        self.session_id: Optional[str] = None
        self.session_manager = get_session_manager()
        self.sandbox_config: Optional[SandboxConfig] = None  # 存储沙盒配置
        self.mcp_client = None  # MCP 客户端
        self.setup_agent()
        
    def setup_agent(self, session_id: Optional[str] = None):
        """设置 Agent - 支持会话管理"""
        try:
            # 加载配置
            config_manager = ConfigManager('config.json')
            self.sandbox_config = config_manager.get_config('default')

            # 创建或获取会话
            if session_id:
                self.session_id = session_id
            else:
                self.session_id = self.session_manager.create_session()
            
            logger.info(f"设置Agent - 会话ID: {self.session_id}")

            # 创建支持会话的沙盒工具
            sandbox_tools = create_strands_tools(self.sandbox_config, self.session_id)
            all_tools = sandbox_tools.copy()
            
            # 创建 Bedrock 模型
            bedrock_model = BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                region_name="us-west-2",
                temperature=0.1,
                max_tokens=8000
            )

            # 设置 MCP 工具
            self.mcp_client = None
            try:
                mcp_settings = config_manager.get_raw_config('mcp_settings')
                exa_api_key = mcp_settings.get('exa_api_key')
                
                if exa_api_key:
                    from mcp import stdio_client, StdioServerParameters
                    from strands.tools.mcp import MCPClient
                    
                    # 创建本地 stdio MCP 客户端
                    self.mcp_client = MCPClient(lambda: stdio_client(
                        StdioServerParameters(
                            command="npx",
                            args=["-y", "exa-mcp-server", "--tools=web_search_exa, crawling, wikipedia_search_exa,github_search, company_research,linkedin_search"],
                            env={"EXA_API_KEY": exa_api_key}
                        )
                    ))
                    
                    # 一次性获取 MCP 工具
                    with self.mcp_client:
                        mcp_tools = self.mcp_client.list_tools_sync()
                        all_tools = sandbox_tools + mcp_tools
                        logger.info(f"已集成 {len(mcp_tools)} 个 MCP 工具")
                else:
                    logger.warning("MCP设置中未配置Exa API Key")
            except Exception as e:
                logger.warning(f"MCP集成失败: {e}")
                self.mcp_client = None
            
            # 创建包含所有工具的 Agent
            self.agent = Agent(
                model=bedrock_model,
                tools=all_tools,
                system_prompt=SYSTEM_PROMPT
            )
            
            logger.info(f"Agent 初始化成功，共 {len(all_tools)} 个工具")
            
        except Exception as e:
            logger.error(f"Agent 初始化失败: {e}")
            self.agent = None
    
    def get_sandbox_env_info(self):
        """获取沙盒配置信息"""
        if not self.sandbox_config:
            return "沙盒配置未加载"
        
        try:
            config_info = f"**📦 沙盒环境配置**\n\n"
            config_info += f"- 🖥️ **实例ID**: `{self.sandbox_config.instance_id}`\n"
            config_info += f"- 🌍 **区域**: `{self.sandbox_config.region}`\n"
            # 运行时支持
            if self.sandbox_config.allowed_runtimes:
                runtimes = ', '.join([f"`{rt}`" for rt in self.sandbox_config.allowed_runtimes])
                config_info += f"- 🚀 **支持运行时**: {runtimes}\n"
            config_info += f"- ⏱️ **最大执行时间**: {self.sandbox_config.max_execution_time}秒\n"
            config_info += f"- 💾 **最大内存**: {self.sandbox_config.max_memory_mb}MB\n"
            config_info += f"- 🧹 **清理时间**: {self.sandbox_config.cleanup_after_hours}小时"

            return config_info
        except Exception as e:
            logger.error(f"获取沙盒配置信息失败: {e}")
            return "获取沙盒配置信息失败"
    
    def clear_file_info(self):
        """清空文件信息并重置Agent会话历史"""
        # 清空Agent的消息历史
        if self.agent and hasattr(self.agent, 'messages'):
            messages_count = len(self.agent.messages)
            self.agent.messages = []
            logger.info(f"已清理{messages_count}条Agent历史消息")
        
        # 清空会话的对话计数器
        if self.session_id:
            self.session_manager.clear_session(self.session_id)
            logger.info(f"已清空会话对话记录: {self.session_id}")
        
        # 返回清空后的会话信息和文件信息
        return self.get_session_info(), "暂无文件信息"
    
    def get_session_info(self):
        """获取会话统计信息"""
        if not self.session_id:
            return "暂无会话信息"
        
        try:
            session_stats = self.session_manager.get_session_stats()
            current_session = None
            for session in session_stats['sessions']:
                if session['session_id'] == self.session_id:
                    current_session = session
                    break
            
            info_parts = []

            # 沙盒环境信息
            config_info = self.get_sandbox_env_info()
            info_parts.append(config_info)

            # 会话信息
            if current_session:
                stats_info = f"**🆔 会话信息** (`{self.session_id}`)\n\n"
                stats_info += f"- 🕐 **会话时长**: {current_session['age_minutes']:.1f} 分钟\n"
                stats_info += f"- 📅 **创建时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_session['created_at']))}\n"
                stats_info += f"- 🔄 **最后活动**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_session['last_activity']))}\n"
                info_parts.append(stats_info)
            else:
                info_parts.append("会话信息未找到")

            return "\n\n".join(info_parts)

        except Exception as e:
            logger.error(f"获取会话信息失败: {e}")
            return "获取会话信息失败"
    
    def get_file_info(self):
        """获取当前文件信息"""
        if not self.agent or not hasattr(self.agent, 'messages'):
            return "暂无文件信息"
        
        try:
            tool_results = extract_tool_results_from_messages(self.agent.messages)
            formatted_info = format_file_info(tool_results, self.sandbox_config.base_sandbox_dir)
            
            if not formatted_info or formatted_info.strip() == "":
                return "暂无文件信息"
            
            return formatted_info
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return "获取文件信息失败"
    
    def refresh_status(self):
        """刷新会话信息和文件信息"""
        return self.get_session_info(), self.get_file_info()

    def chat_with_agent(self, message: str, history: List[Dict]) -> Generator[tuple, None, None]:
        """与 Agent 聊天 - 支持流式输出，返回 (聊天消息, 会话信息, 文件信息)"""

        # 输入验证
        if not message or not message.strip():
            yield ([ChatMessage(
                role="assistant",
                content="请输入有效的消息。",
                metadata={"title": "⚠️ 输入错误"}
            )], self.get_session_info(), self.get_file_info())
            return
            
        if not self.agent:
            yield ([ChatMessage(
                role="assistant",
                content="❌ Agent 未正确初始化，请检查配置。",
                metadata={"title": "🚨 系统错误"}
            )], self.get_session_info(), self.get_file_info())
            return

        # 显示初始状态
        stat_msg = ChatMessage(
            role="assistant",
            content="正在分析您的请求...",
            metadata={
                "title": "🧠 Thinking",
                "status": "pending"
            }
        )
        yield ([stat_msg], self.get_session_info(), self.get_file_info())

        try:
           # 使用线程来运行异步代码，实现真正的流式输出
            import threading
            import queue

            start_time = time.time()

            # 创建队列来传递流式数据
            stream_queue = queue.Queue()
            exception_container: List[Optional[Exception]] = [None]
            
            def async_stream_worker():
                """在独立线程中运行异步流式处理"""
                loop = None
                try:
                    # 创建新的事件循环
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    
                    async def stream_handler():
                        try:
                            if self.agent is None:
                                stream_queue.put("❌ Agent 未正确初始化, 请检查配置。")
                                return

                            full_response = ""
                            first_chunk = True

                            # 简单直接：如果有 MCP 客户端就在其 context 中执行
                            if self.mcp_client:
                                with self.mcp_client:
                                    async for event in self.agent.stream_async(message):
                                        if "data" in event:
                                            chunk = event["data"]
                                            if first_chunk:
                                                full_response = chunk
                                                first_chunk = False
                                            else:
                                                full_response += chunk
                                            stream_queue.put(full_response)
                            else:
                                # 没有 MCP，直接执行
                                async for event in self.agent.stream_async(message):
                                    if "data" in event:
                                        chunk = event["data"]
                                        if first_chunk:
                                            full_response = chunk
                                            first_chunk = False
                                        else:
                                            # 累积后续文本块
                                            full_response += chunk
                                        stream_queue.put(full_response)
                                    
                        except Exception as e:
                            logger.error(f"流式处理失败: {e}")
                            error_msg = f"抱歉，执行过程中遇到错误：\n\n```\n{str(e)}\n```\n\n请尝试重新描述您的需求，或者检查网络连接。"
                            stream_queue.put(error_msg)                             

                        finally:
                            # 发送结束信号
                            stream_queue.put(None)
                    
                    # 运行异步处理
                    loop.run_until_complete(stream_handler())

                except Exception as e:
                    exception_container[0] = e
                    stream_queue.put(None)
                finally:
                    if loop is not None:
                        loop.close()
            
            # 启动异步处理线程
            thread = threading.Thread(target=async_stream_worker)
            thread.daemon = True
            thread.start()
            
            # 实时从队列中获取并输出数据
            last_content = ""
            while True:
                try:
                    # 等待数据，设置超时避免无限等待
                    chunk = stream_queue.get(timeout=180)

                    if chunk is None:
                        # 收到结束信号
                        if last_content:
                            duration = time.time() - start_time
                            stat_msg.content = f"处理完成。耗时: {duration:.1f}s"
                            stat_msg.metadata = {
                                "title": "✅ Done",
                                "status": "done"
                            }
                            yield ([stat_msg, ChatMessage(role="assistant", content=last_content)], self.get_session_info(), self.get_file_info())
                        break
                    
                    # 正常的流式内容
                    if chunk and chunk.strip():
                        last_content = chunk  # 保存最后的内容
                        stat_msg.content = f"正在执行 ..."
                        stat_msg.metadata = {
                            "title": "🔄 Processing", 
                            "status": "pending"
                        }
                        yield ([stat_msg, ChatMessage(role="assistant", content=chunk)], self.get_session_info(), self.get_file_info())

                except queue.Empty:
                    # 超时，检查是否有异常
                    if exception_container[0]:
                        yield ([ChatMessage(
                            role="assistant",
                            content=f"处理超时或出现异常: {exception_container[0]}",
                            metadata={"title": "🚨 错误详情"}
                        )], self.get_session_info(), self.get_file_info())
                        break
                    else:
                        yield ([ChatMessage(
                            role="assistant",
                            content="处理超时，请重试",
                            metadata={"title": "🚨 错误详情"}
                        )], self.get_session_info(), self.get_file_info())
                        break
            
            # 等待线程结束
            thread.join(timeout=30)

        except Exception as e:
            logger.error(f"同步包装函数失败: {e}")
            # 显示错误信息
            yield ([ChatMessage(
                role="assistant",
                content=f"抱歉，执行过程中遇到错误：\n\n```\n{str(e)}\n```\n\n请尝试重新描述您的需求，或者检查网络连接。",
                metadata={"title": "🚨 错误详情"}
            )], self.get_session_info(), self.get_file_info())

def create_demo():
    """创建 Gradio Demo UI"""
    
    # 初始化 Demo 类
    demo_instance = EC2SandboxDemo()
    css = f""" 
    footer {{visibility: hidden}}
    """

    with gr.Blocks(title="EC2 Sandbox Agent Demo", css=css) as demo:
        gr.Markdown("""
                    # 🚀 EC2 Sandbox Agent Demo
                    **基于 Strands Agents 构建的 AI 智能助手！**
                    
                    本演示使用运行在 AWS EC2 实例上的代码执行环境，支持：
                    - 🧑‍💻 **Python** (pandas, numpy, matplotlib, plotly, scipy等)
                        - 📊 **数据分析** (预置的数据科学工具栈)
                    - 🧑‍💻 **Node.js** (JavaScript运行时)
                    - 🛠️ **Bash/Shell** (系统脚本)
                    - 📁 **文件管理** (自动文件创建和管理)
                    """)
        with gr.Row():
            with gr.Column(scale=2):
                # 定义Chatbot组件
                chatbot = gr.Chatbot(
                    type='messages',
                    show_copy_button=True,
                    min_height='60vh',
                    max_height='80vh',
                    allow_tags=True,
                    render=False
                )

                session_info = gr.Markdown(
                    label="📊 会话信息",
                    show_label=True,
                    container=True,
                    value="",
                    render=False
                )

                file_info = gr.Markdown(
                    label="📁 文件信息",
                    show_label=True,
                    container=True,
                    value="暂无文件信息",
                    render=False
                )

                # 创建聊天界面
                chat_interface = gr.ChatInterface(
                    fn=demo_instance.chat_with_agent,
                    type="messages",
                    chatbot=chatbot,
                    additional_outputs=[session_info, file_info],
                    examples=[
                        "写一个Node.js程序计算前21个斐波那契数",
                        "查询最新的AWS区域信息并保存到JSON文件",
                        "创建一个Bash脚本来统计当前目录的文件信息",
                        "用Python创建一个简单的数据分析脚本, 分析销售数据并生成报告",
                        "用matplotlib创建一个包含多个子图的数据可视化",
                        "从datasciencedojo Github repo下载Boston房价数据集, 用pandas进行数据分析并生成统计摘要和可视化报告"
                    ],
                    theme='soft'
                )

            with gr.Column(scale=1):
                # 添加刷新按钮
                refresh_btn = gr.Button("🔄 刷新状态(Sandbox)", variant="secondary")
                session_info.render()
                file_info.render()

                # 绑定刷新事件
                refresh_btn.click(
                    fn=demo_instance.refresh_status,
                    outputs=[session_info, file_info]
                )
                
                # 监听chatbot clear事件，同时清空文件信息
                chat_interface.chatbot.clear(
                    fn=demo_instance.clear_file_info,
                    outputs=[session_info, file_info]
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
        server_port=8086,
        share=False,            # 不创建公共链接
        debug=False,
        show_error=True,        # 显示错误信息
        show_api=False,         # 隐藏 API 文档
        allowed_paths=[],       # 允许的静态文件路径
    )

if __name__ == "__main__":
    main()
