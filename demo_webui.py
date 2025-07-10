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

def format_file_info(tool_results):
    """格式化文件信息显示"""
    if not tool_results:
        return "暂无文件信息"
    
    # 过滤掉无效的工具结果 - 只保留有工作目录和任务哈希的任务
    valid_results = []
    for result in tool_results:
        # 只保留有效的执行结果（有任务哈希）
        if task_hash := result.get('task_hash'):
            valid_results.append(result)

    if not valid_results:
        return "暂无有效的文件信息"
    
    info_lines = []
    session_displayed = False
    
    for i, result in enumerate(valid_results):
        # 只在第一次显示会话信息
        if not session_displayed:
            session_id = result.get('session_id', 'N/A')
            if session_id != 'N/A':
                info_lines.append(f"**🔗 沙盒执行** (sid:{session_id})")
                info_lines.append("")  # 空行
                session_displayed = True
        
        # 任务信息
        info_lines.append(f"**📋 任务 {i+1}**")
        
        working_directory = result.get('working_directory', '')
        task_hash = result.get('task_hash', None)
        # 屏蔽敏感的工作目录路径
        masked_dir = f"./{task_hash}" if task_hash else "N/A"
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
        """初始化 SandboxDemo"""
        self.session_manager = get_session_manager()
        self.sandbox_config: Optional[SandboxConfig] = None
        self.mcp_client = None
        self.mcp_tools = []  # 存储MCP工具
        self.user_agents = {}  # 存储每个用户的 Agent 实例
        
        # 加载配置
        self.load_config()
        
        # 初始化MCP工具（一次性，所有session复用）
        self.setup_mcp_tools()
        
    def load_config(self):
        """加载配置"""
        try:
            config_manager = ConfigManager('config.json')
            self.sandbox_config = config_manager.get_sandbox_config('sandbox-default')
            logger.info("配置加载成功")
        except Exception as e:
            logger.error(f"配置加载失败: {e}")
            raise
    
    def setup_mcp_tools(self):
        """设置MCP工具（一次性初始化，所有session复用）"""
        try:
            config_manager = ConfigManager('config.json')
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
                    self.mcp_tools = self.mcp_client.list_tools_sync()
                    logger.info(f"已集成 {len(self.mcp_tools)} 个 MCP 工具")
            else:
                logger.warning("MCP设置中未配置Exa API Key")
        except Exception as e:
            logger.warning(f"MCP集成失败: {e}")
            self.mcp_client = None
            self.mcp_tools = []
    
    def get_or_create_agent_for_session(self, session_id: str) -> Agent:
        """为指定会话获取或创建 Agent"""
        if session_id not in self.user_agents:
            logger.info(f"为会话创建新的 Agent: {session_id}")
            
            # 确保 sandbox_config 不为 None
            if self.sandbox_config is None:
                raise RuntimeError("沙盒配置未初始化")
            
            # 直接使用传入的session_id（即Gradio的session_hash）
            sandbox_tools = create_strands_tools(self.sandbox_config, session_id)
            all_tools = sandbox_tools.copy()
            
            # 添加预初始化的MCP工具
            if self.mcp_tools:
                all_tools = sandbox_tools + self.mcp_tools
                logger.info(f"已集成 {len(self.mcp_tools)} 个 MCP 工具")
            
            # 创建BedrockModel
            bedrock_model = BedrockModel(
                model_id="us.anthropic.claude-3-5-sonnet-20241022-v2:0",
                region_name="us-west-2",
                temperature=0.1,
                max_tokens=4000
            )
            
            # 创建Agent
            agent = Agent(
                model=bedrock_model,
                system_prompt=SYSTEM_PROMPT,
                tools=all_tools
            )
            
            self.user_agents[session_id] = agent
            logger.info(f"Agent 初始化成功，共 {len(all_tools)} 个工具")
        
        return self.user_agents[session_id]

    def _get_state_emoji(self, state: str) -> str:
        """根据实例状态返回对应的emoji"""
        state_emojis = {
            'running': '🟢',      # 绿色圆点 - 运行中
            'stopped': '🔴',      # 红色圆点 - 已停止
            'shutting-down': '🟠', # 橙色圆点 - 关闭中
            'terminated': '⚫',    # 黑色圆点 - 已终止
            'rebooting': '🔄',    # 循环箭头 - 重启中
        }
        return state_emojis.get(state.lower(), '🟡')  # 默认问号

    def get_sandbox_env_info(self):
        """获取沙盒环境信息，包括配置和实时状态"""
        if not self.sandbox_config:
            return "沙盒配置未加载"
        
        try:
            config_info = f"**📦 沙盒环境信息**\n\n"

            # 获取实例信息
            try:
                from ec2_sandbox.core import EC2SandboxEnv
                sandbox_env = EC2SandboxEnv(self.sandbox_config)
                status = sandbox_env.check_instance_status()
            # 基本配置信息
                config_info += f"- 🖥️ **实例类型**: `{status.get('instance_type', 'Unknown')}` (`{self.sandbox_config.instance_id}`)\n"
                config_info += f"- 🌍 **区域**: `{self.sandbox_config.region}`\n"
                            
                if 'error' not in status:
                    state_emoji = self._get_state_emoji(status.get('state', 'unknown'))
                    # CPU使用率
                    cpu_info = status.get('cpu_utilization', {})
                    if 'error' not in cpu_info and 'message' not in cpu_info:
                        cpu_avg = cpu_info.get('average', 0)
                        config_info += f"- {state_emoji} **CPU使用率**: {cpu_avg}%（平均）\n"
                    else:
                        config_info += f"- ❌ **CPU使用率**: 获取失败\n"
                else:
                    config_info += f"- ❌ **状态**: {status.get('error', '获取失败')}\n"
                    
            except Exception as e:
                logger.warning(f"获取实例状态失败: {e}")
                config_info += f"- ⚠️ **状态**: 无法获取实时信息\n"
            
            # 配置信息
            config_info += f"\n**⚙️ 配置参数**\n"
            
            # 运行时支持
            if self.sandbox_config.allowed_runtimes:
                runtimes = ', '.join([f"`{rt}`" for rt in self.sandbox_config.allowed_runtimes])
                config_info += f"- 🚀 **支持运行时**: {runtimes}\n"
            config_info += f"- ⏱️ **最大执行时间**: {self.sandbox_config.max_execution_time}秒\n"
            config_info += f"- 💾 **最大内存**: {self.sandbox_config.max_memory_mb}MB\n"
            config_info += f"- 🧹 **清理时间**: {self.sandbox_config.cleanup_after_hours}小时"

            return config_info
        except Exception as e:
            logger.error(f"获取沙盒环境信息失败: {e}")
            return "获取沙盒环境信息失败"
    
    def clear_chat_status(self, request: gr.Request):
        """清空文件信息并重置Agent会话历史"""
        try:
            session_id = request.session_hash if request else None
            
            # 确保 session_id 不为 None
            if session_id is None:
                session_id = f"fallback_{int(time.time())}"
            
            # 清空Agent历史消息
            if session_id in self.user_agents:
                agent = self.user_agents[session_id]
                if agent and hasattr(agent, 'messages'):
                    messages_count = len(agent.messages)
                    agent.messages = []
                    logger.info(f"已清理会话 {session_id} 的 {messages_count} 条Agent消息")
            
            # 清空会话的对话计数器
            try:
                self.session_manager.clear_session(session_id)
                logger.info(f"已清空会话 {session_id} 的记录")
            except Exception as e:
                logger.warning(f"清空会话记录失败: {e}")
            
            # 返回清空后的会话信息和文件信息
            return self.get_session_info(session_id), "暂无文件信息"
            
        except Exception as e:
            logger.error(f"清空聊天状态失败: {e}")
            return "清空操作失败", "清空操作失败"
    
    def get_session_info(self, session_id: str):
        """获取当前用户会话的统计信息"""
        if not session_id:
            return "暂无会话信息"

        try:
            session_stats = self.session_manager.get_session_stats()
            current_session = None
            for session in session_stats['sessions']:
                if session['session_id'] == session_id:
                    current_session = session
                    break
            
            info_parts = []

            # 会话信息
            if current_session:
                stats_info = f"**🆔 当前会话** (`{session_id}`)\n\n"
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
    
    def get_file_info(self, session_id: str):
        """获取当前请求的文件信息"""
        if not session_id or session_id not in self.user_agents:
            return "暂无文件信息"

        agent = self.user_agents[session_id]
        if not agent or not hasattr(agent, 'messages'):
            return "暂无文件信息"
        
        try:
            tool_results = extract_tool_results_from_messages(agent.messages)
            formatted_info = format_file_info(tool_results)
            
            if not formatted_info or formatted_info.strip() == "":
                return "暂无文件信息"
            
            return formatted_info
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return "获取文件信息失败"
    
    def initialize_session(self, request: gr.Request):
        """页面加载时初始化用户会话"""
        session_id = (request.session_hash if request else None) or f"sid-{int(time.time())}"

        # 确保会话在 session_manager 中存在
        self.session_manager.get_or_create_session(session_id)
        logger.info(f"页面加载时初始化会话: {session_id}")
        
        return self.get_session_info(session_id)
    
    def refresh_status(self, request: gr.Request):
        """刷新会话信息和文件信息"""
        session_id = (request.session_hash if request else None) or f"sid-{int(time.time())}"

        return self.get_session_info(session_id), self.get_file_info(session_id)

    def chat_with_agent(self, message: str, history: List[Dict], request: gr.Request) -> Generator[tuple, None, None]:
        """与 Agent 聊天 - 支持流式输出，返回 (聊天消息, 会话信息, 文件信息)"""
        
        # 使用 Gradio 的 session_hash 作为 session ID
        session_id = (request.session_hash if request else None) or f"sid-{int(time.time())}"

        # 为这个会话获取或创建 Agent
        agent = self.get_or_create_agent_for_session(session_id)

        # 输入验证
        if not message or not message.strip():
            yield ([ChatMessage(
                role="assistant",
                content="请输入有效的消息。",
                metadata={"title": "⚠️ 输入错误"}
            )], self.get_session_info(session_id), self.get_file_info(session_id))
            return
            
        if not agent:
            yield ([ChatMessage(
                role="assistant",
                content="❌ Agent 未正确初始化，请检查配置。",
                metadata={"title": "🚨 系统错误"}
            )], self.get_session_info(session_id), self.get_file_info(session_id))
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
        yield ([stat_msg], self.get_session_info(session_id), self.get_file_info(session_id))

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
                            if agent is None:
                                stream_queue.put("❌ Agent 未正确初始化, 请检查配置。")
                                return

                            full_response = ""
                            first_chunk = True

                            # 简单直接：如果有 MCP 客户端就在其 context 中执行
                            if self.mcp_client:
                                with self.mcp_client:
                                    async for event in agent.stream_async(message):
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
                                async for event in agent.stream_async(message):
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
                            yield ([stat_msg, ChatMessage(role="assistant", content=last_content)], self.get_session_info(session_id), self.get_file_info(session_id))
                        break
                    
                    # 正常的流式内容
                    if chunk and chunk.strip():
                        last_content = chunk  # 保存最后的内容
                        stat_msg.content = f"正在执行 ..."
                        stat_msg.metadata = {
                            "title": "🔄 Processing", 
                            "status": "pending"
                        }
                        yield ([stat_msg, ChatMessage(role="assistant", content=chunk)], self.get_session_info(session_id), self.get_file_info(session_id))

                except queue.Empty:
                    # 超时，检查是否有异常
                    if exception_container[0]:
                        yield ([ChatMessage(
                            role="assistant",
                            content=f"处理超时或出现异常: {exception_container[0]}",
                            metadata={"title": "🚨 错误详情"}
                        )], self.get_session_info(session_id), self.get_file_info(session_id))
                        break
                    else:
                        yield ([ChatMessage(
                            role="assistant",
                            content="处理超时，请重试",
                            metadata={"title": "🚨 错误详情"}
                        )], self.get_session_info(session_id), self.get_file_info(session_id))
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
            )], self.get_session_info(session_id), self.get_file_info(session_id))

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

                textbox = gr.Textbox(
                    placeholder="Type a message here",
                    submit_btn=True,
                    stop_btn=True,
                    render=False
                )

                sandbox_env_info = gr.Markdown(
                    label="📦 沙盒环境信息",
                    show_label=True,
                    container=True,
                    value="",
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
                    textbox=textbox,
                    additional_outputs=[session_info, file_info],
                    examples=[
                        "写一个Node.js程序计算前21个斐波那契数",
                        "查询最新的AWS区域信息并保存到JSON文件",
                        "创建一个Bash脚本来统计当前目录的文件信息",
                        "用matplotlib创建一个包含多个子图的数据可视化",
                        "用Python创建一个简单的数据分析脚本, 分析销售数据并生成报告",
                        "从datasciencedojo Github repo下载Boston房价数据集, 用pandas进行数据分析并生成统计报告"
                    ],
                    theme='soft'
                )

            with gr.Column(scale=1):
                sandbox_env_info.render()
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
            # chat_interface.chatbot.clear(
            #     fn=demo_instance.clear_chat_status,
            #     outputs=[session_info, file_info]
            # )

            chat_interface.load(
                fn=demo_instance.get_sandbox_env_info,
                outputs=[sandbox_env_info]
            )
            
            # 页面加载时初始化会话
            demo.load(
                fn=demo_instance.initialize_session,
                outputs=[session_info]
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
