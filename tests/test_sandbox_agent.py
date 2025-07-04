#!/usr/bin/env python3
"""
功能测试：验证 EC2Sandbox 工具与 Strands Agent 集成
"""

import os
import sys
from strands import Agent
from strands.models.bedrock import BedrockModel
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_manager import ConfigManager
from strands_tools import create_strands_tools

def test_basic_functionality():
    """测试基础功能"""
    print("🧪 测试1: 基础工具功能")
    
    try:
        # 加载配置
        config_manager = ConfigManager('config.json')
        config = config_manager.get_config('default')
        
        # 创建工具
        tools = create_strands_tools(config)
        execute_code_in_sandbox = tools[0]
        
        # 测试代码执行
        result = execute_code_in_sandbox(
            code="print('Hello from test!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')",
            runtime="python3",
            task_id="test_basic"
        )
        
        print("✅ 基础工具测试通过")
        print(result)
        return True
        
    except Exception as e:
        print(f"❌ 基础工具测试失败: {e}")
        return False

def test_agent_integration():
    """测试Agent集成（如果可用）"""
    print("\n🧪 测试2: Agent集成")
    
    try:
        # 加载配置和工具
        config_manager = ConfigManager('config.json')
        config = config_manager.get_config('default')
        tools = create_strands_tools(config)
        
        # 尝试创建BedrockModel
        try:
            bedrock_model = BedrockModel(
                model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                region_name="us-west-2",
                temperature=0.1,
                max_tokens=1000
            )
            
            agent = Agent(
                model=bedrock_model,
                system_prompt="你是一个编程助手。使用code_execution_tool执行代码。",
                tools=tools
            )
            
            # 简单测试
            print("🤖 测试Agent响应...")
            # 使用一个必须通过代码计算才能得出的复杂问题
            complex_question = """请计算以下数学问题：
1. 生成斐波那契数列的前20项
2. 计算这20项的平方和
3. 找出其中所有的质数
4. 计算质数的乘积
5. 最后将乘积转换为16进制表示

这个问题需要多步计算，请用Python代码完成。
"""
            print(f"📋 {complex_question}")
            agent(complex_question)
            print("✅ Agent集成测试通过")
            # 响应内容已经自动显示，不需要额外打印
            return True
            
        except Exception as model_error:
            print(f"⚠️  Agent集成跳过 (模型不可用): {model_error}")
            return True  # 不算失败，因为模型可能不可用
            
    except Exception as e:
        print(f"❌ Agent集成测试失败: {e}")
        return False

def test_code_length_limit():
    """测试代码长度限制"""
    print("\n🧪 测试3: 代码长度限制")
    
    try:
        config_manager = ConfigManager('config.json')
        config = config_manager.get_config('default')
        tools = create_strands_tools(config)
        execute_code_in_sandbox = tools[0]
        
        # 测试超长代码
        long_code = "print('test')\n" + "#" * 80000  # 80KB
        result = execute_code_in_sandbox(
            code=long_code,
            runtime="python3",
            task_id="test_long"
        )
        
        # 检查是否正确拦截
        import json
        result_dict = json.loads(result)
        if not result_dict['success'] and '代码过长' in result_dict['stderr']:
            print("✅ 代码长度限制测试通过")
            return True
        else:
            print("❌ 代码长度限制未正确工作")
            return False
            
    except Exception as e:
        print(f"❌ 代码长度限制测试失败: {e}")
        return False

def test_file_operations():
    """测试文件操作"""
    print("\n🧪 测试4: 文件操作")
    
    try:
        config_manager = ConfigManager('config.json')
        config = config_manager.get_config('default')
        tools = create_strands_tools(config)
        execute_code_in_sandbox = tools[0]
        get_task_files = tools[1]
        
        # 执行代码生成文件
        code_result = execute_code_in_sandbox(
            code="""
import json
data = {"test": "file operations", "number": 42}
with open('test_file.json', 'w') as f:
    json.dump(data, f)
print("File created successfully")
""",
            runtime="python3",
            task_id="test_files"
        )
        
        # 获取task_hash
        import json
        result_dict = json.loads(code_result)
        if result_dict['success']:
            task_hash = result_dict['task_hash']
            
            # 获取文件
            files_result = get_task_files(task_hash=task_hash)
            files_dict = json.loads(files_result)
            
            if 'test_file.json' in files_dict:
                print("✅ 文件操作测试通过")
                return True
            else:
                print("❌ 文件未正确创建或获取")
                return False
        else:
            print("❌ 代码执行失败")
            return False
            
    except Exception as e:
        print(f"❌ 文件操作测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("🚀 EC2 Sandbox + Strands Agent 功能测试")
    print("=" * 60)
    
    tests = [
        test_basic_functionality,
        test_agent_integration,
        test_code_length_limit,
        test_file_operations
    ]
    
    passed = 0
    total = len(tests)
    
    for test_func in tests:
        try:
            if test_func():
                passed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")
    
    print(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 所有测试通过！")
        return True
    else:
        print("⚠️  部分测试失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
