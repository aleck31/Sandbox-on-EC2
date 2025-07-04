#!/usr/bin/env python3
"""
测试代码长度检查功能
"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_manager import ConfigManager
from strands_tools import create_strands_tools


def test_code_length_check():
    """测试代码长度检查"""
    
    config_manager = ConfigManager('config.json')
    config = config_manager.get_config('default')
    tools = create_strands_tools(config)
    execute_code_in_sandbox = tools[0]
    
    print("🧪 测试代码长度检查功能")
    
    # 测试1: 正常长度的代码
    print("\n1️⃣ 测试正常长度代码 (1KB)")
    normal_code = """
print("Hello World!")
for i in range(10):
    print(f"Number: {i}")
result = sum(range(100))
print(f"Sum: {result}")
"""
    
    result = execute_code_in_sandbox(
        code=normal_code,
        runtime="python3",
        task_id="test_normal"
    )
    
    result_dict = json.loads(result)
    print(f"   结果: {'✅ 成功' if result_dict['success'] else '❌ 失败'}")
    if not result_dict['success']:
        print(f"   错误: {result_dict['stderr'][:100]}...")
    
    # 测试2: 超长代码 (80KB)
    print("\n2️⃣ 测试超长代码 (80KB)")
    base_code = "print('Long code test')\n"
    long_code = base_code + "#" * (80 * 1024 - len(base_code))
    
    result = execute_code_in_sandbox(
        code=long_code,
        runtime="python3", 
        task_id="test_long"
    )
    
    result_dict = json.loads(result)
    print(f"   结果: {'✅ 成功' if result_dict['success'] else '❌ 失败 (预期)'}")
    if not result_dict['success']:
        print(f"   错误信息包含限制说明: {'✅ 是' if '代码过长' in result_dict['stderr'] else '❌ 否'}")
        print(f"   错误信息包含优化建议: {'✅ 是' if '优化建议' in result_dict['stderr'] else '❌ 否'}")
    
    # 测试3: 边界测试 (70KB)
    print("\n3️⃣ 测试边界代码 (70KB)")
    boundary_code = base_code + "#" * (70 * 1024 - len(base_code))
    
    result = execute_code_in_sandbox(
        code=boundary_code,
        runtime="python3",
        task_id="test_boundary"
    )
    
    result_dict = json.loads(result)
    print(f"   结果: {'✅ 成功' if result_dict['success'] else '❌ 失败'}")
    if not result_dict['success']:
        print(f"   错误: {result_dict['stderr'][:100]}...")

if __name__ == "__main__":
    test_code_length_check()
