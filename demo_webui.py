#!/usr/bin/env python3
"""
EC2 Sandbox Agent - Gradio Demo
基于 Gradio 的 Agent 演示界面，展示 Strands Agents + EC2沙盒代码执行能力
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
    
    info_lines = []
    for i, result in enumerate(tool_results):
        info_lines.append(f"**任务 #{i+1}**")
        info_lines.append(f"- 📁 任务ID: `{result.get('task_hash', 'N/A')}`")
        info_lines.append(f"- 📂 工作目录: `{result.get('working_directory', 'N/A')}`")
        
        files_created = result.get('files_created', [])
        if files_created:
            info_lines.append(f"- 📄 创建的文件: {', '.join([f'`{f}`' for f in files_created])}")
        
        execution_time = result.get('execution_time')
        if execution_time:
            info_lines.append(f"- ⏱️ 执行时间: {execution_time:.2f}秒")
        
        return_code = result.get('return_code')
        if return_code is not None:
            status = "✅ 成功" if return_code == 0 else "❌ 失败"
            info_lines.append(f"- 📊 执行状态: {status}")
        
        info_lines.append("")  # 空行分隔
    
    return "\n".join(info_lines)

class EC2SandboxDemo:
    """EC2 Sandbox Agent Demo 类"""
    
    def __init__(self):
        """初始化 Demo"""
        self.agent: Optional[Agent] = None
        self.file_info_state = gr.State("暂无文件信息")
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
    
    def get_file_info(self):
        """获取当前文件信息"""
        if not self.agent or not hasattr(self.agent, 'messages'):
            return "暂无文件信息"
        
        try:
            tool_results = extract_tool_results_from_messages(self.agent.messages)
            return format_file_info(tool_results)
        except Exception as e:
            logger.error(f"获取文件信息失败: {e}")
            return "获取文件信息失败"
    
    def chat_with_agent(self, message: str, history: List[Dict]) -> Generator[List[gr.ChatMessage], None, None]:
        """与 Agent 聊天 - 支持流式输出"""
        
        if not self.agent:
            yield [ChatMessage(
                role="assistant",
                content="❌ Agent 未正确初始化，请检查配置。",
                metadata={"title": "🚨 系统错误"}
            )]
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
        yield [stat_msg]

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

                            async for event in self.agent.stream_async(message):
                                if "data" in event:
                                    chunk = event["data"]
                                    
                                    if first_chunk:
                                        # 第一个数据块时替换状态消息
                                        full_response = chunk
                                        first_chunk = False
                                    else:
                                        # 累积后续文本块
                                        full_response += chunk
                                    
                                    # 立即放入队列
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
                            stat_msg.content = f"处理完成。耗时: {duration} \n"
                            stat_msg.metadata = {
                                "title": "✅ Done",
                                "status": "done"
                            }
                            yield [stat_msg, ChatMessage(role="assistant",content=last_content)]
                        break
                    
                    # 正常的流式内容
                    if chunk and chunk.strip():
                        last_content = chunk  # 保存最后的内容
                        stat_msg.content = f"正在执行 ..."
                        stat_msg.metadata = {
                            "title": "🔄 Processing", 
                            "status": "pending"
                        }
                        yield [stat_msg, ChatMessage(role="assistant",content=chunk)]

                except queue.Empty:
                    # 超时，检查是否有异常
                    if exception_container[0]:
                        yield [ChatMessage(
                            role="assistant",
                            content=f"处理超时或出现异常: {exception_container[0]}",
                            metadata={"title": "🚨 错误详情"}
                        )]
                        break
                    else:
                        yield [ChatMessage(
                            role="assistant",
                            content="处理超时，请重试",
                            metadata={"title": "🚨 错误详情"}
                        )]
                        break
            
            # 等待线程结束
            thread.join(timeout=30)

        except Exception as e:
            logger.error(f"同步包装函数失败: {e}")
            # 显示错误信息
            yield [ChatMessage(
                role="assistant",
                content=f"抱歉，执行过程中遇到错误：\n\n```\n{str(e)}\n```\n\n请尝试重新描述您的需求，或者检查网络连接。",
                metadata={"title": "🚨 错误详情"}
            )]

def create_demo():
    """创建 Gradio Demo"""
    
    # 初始化 Demo 类
    demo_instance = EC2SandboxDemo()
    css = f""" 
    footer {{visibility: hidden}}
    """

    with gr.Blocks(title="EC2 Sandbox Agent Demo", css=css) as demo:
        gr.Markdown("""
                    # 🚀 EC2 Sandbox Agent Demo
                    **基于 Strands Agents 构建的代码执行助手！**
                    
                    这是一个运行在 AWS EC2 实例上的代码执行环境，支持：
                    - 🐍 **Python** (pandas, numpy, matplotlib, plotly, scipy等)
                        - 📊 **数据分析** (预置的数据科学工具栈)
                    - 🟢 **Node.js** (JavaScript运行时)
                    - 🐚 **Bash/Shell** (系统脚本)
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
                # 创建聊天界面
                chat_interface = gr.ChatInterface(
                    fn=demo_instance.chat_with_agent,
                    type="messages",
                    chatbot=chatbot,
                    examples=[
                        "写一个Node.js程序计算前21个斐波那契数",
                        "创建一个Bash脚本来统计当前目录的文件信息",
                        "用Python创建一个简单的数据分析脚本, 分析销售数据并生成报告",
                        "用matplotlib创建一个包含多个子图的数据可视化",
                        "用pandas处理CSV数据并生成统计摘要"
                    ],
                    theme='soft'
                )

            with gr.Column(scale=1):
                # 添加刷新按钮
                refresh_btn = gr.Button("🔄 刷新文件信息(Sandbox)", variant="secondary")

                file_info = gr.Markdown(
                    label="📁 文件信息",
                    value="暂无文件信息"
                )

                # 绑定刷新事件
                refresh_btn.click(
                    fn=demo_instance.get_file_info,
                    outputs=[file_info]
                )
                
                # 监听聊天完成事件，自动刷新文件信息
                chat_interface.chatbot.change(
                    fn=demo_instance.get_file_info,
                    outputs=[file_info],
                    show_progress='hidden'
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
