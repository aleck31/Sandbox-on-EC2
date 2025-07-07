#!/usr/bin/env python3
"""
测试 demo_webui.py 中的文件信息提取功能
"""

from demo_webui import EC2SandboxDemo, extract_tool_results_from_messages, format_file_info

def test_file_info_extraction():
    """测试文件信息提取功能"""
    
    print("🔍 测试 demo_webui.py 中的文件信息提取功能")
    print("=" * 50)
    
    # 初始化 Demo 实例
    demo = EC2SandboxDemo()
    
    if not demo.agent:
        print("❌ Agent 初始化失败")
        return
    
    print("✅ Agent 初始化成功")
    
    # 测试消息
    test_message = "用Python创建一个文本文件：with open('hello.txt', 'w') as f: f.write('Hello World')"
    
    print(f"📤 发送测试消息: {test_message}")
    
    # 执行 Agent 请求（同步方式）
    try:
        response = demo.agent(test_message)
        print(f"✅ Agent 响应完成")
        print(f"响应内容: {str(response)[:200]}...")
        
        # 测试文件信息提取
        print(f"\n🔍 测试文件信息提取:")
        file_info = demo.get_file_info()
        print(f"文件信息:\n{file_info}")
        
        # 直接测试提取函数
        print(f"\n🔍 直接测试提取函数:")
        tool_results = extract_tool_results_from_messages(demo.agent.messages)
        print(f"提取到 {len(tool_results)} 个工具执行结果")
        
        for i, result in enumerate(tool_results):
            print(f"\n工具结果 #{i+1}:")
            print(f"  task_hash: {result.get('task_hash')}")
            print(f"  files_created: {result.get('files_created')}")
            print(f"  working_directory: {result.get('working_directory')}")
            print(f"  execution_time: {result.get('execution_time')}")
        
        print(f"\n✅ 文件信息提取功能测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_file_info_extraction()
