#!/usr/bin/env python3
"""
EC2 Sandbox 测试脚本
用于验证工具的各项功能
"""

import json
import time
import os
import sys

# 添加父目录到路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox import EC2SandboxEnv
from strands_tools import create_strands_tools

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

def test_basic_execution():
    """测试基础代码执行"""
    print("=== 测试基础代码执行 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_basic")
    
    # 简单Python测试
    code = """
print("Hello from test!")
import sys
print(f"Python version: {sys.version_info}")
result = 2 + 2
print(f"2 + 2 = {result}")
"""
    
    try:
        result = sandbox.execute_code(
            code=code,
            runtime="python3",
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"返回码: {result.return_code}")
        print(f"执行时间: {result.execution_time:.2f}s")
        print(f"标准输出:\n{result.stdout}")
        
        if result.stderr:
            print(f"标准错误:\n{result.stderr}")
            
        return result.success
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_file_operations():
    """测试文件操作"""
    print("\n=== 测试文件操作 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_files")
    
    # 准备测试文件
    files = {
        "input.txt": "Hello World!\nThis is a test file.\nLine 3",
        "data.json": json.dumps({"test": True, "value": 42})
    }
    
    code = """
# 读取文件
with open('input.txt', 'r') as f:
    content = f.read()
    print(f"Input file content:\\n{content}")

import json
with open('data.json', 'r') as f:
    data = json.load(f)
    print(f"JSON data: {data}")

# 创建输出文件
with open('output.txt', 'w') as f:
    f.write("Processing completed!\\n")
    f.write(f"Processed {len(content.split())} words\\n")

# 创建结果JSON
result = {
    "input_lines": len(content.split('\\n')),
    "input_words": len(content.split()),
    "json_value": data.get('value', 0) * 2
}

with open('result.json', 'w') as f:
    json.dump(result, f, indent=2)

print("Files created successfully!")
"""
    
    try:
        result = sandbox.execute_code(
            code=code,
            runtime="python3",
            files=files,
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"创建的文件: {result.files_created}")
        print(f"标准输出:\n{result.stdout}")
        
        return result.success
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_environment_variables():
    """测试环境变量"""
    print("\n=== 测试环境变量 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_env")
    
    env_vars = {
        "TEST_VAR": "test_value",
        "NUMBER_VAR": "123",
        "BOOL_VAR": "true"
    }
    
    code = """
import os

print("Environment variables:")
for var in ["TEST_VAR", "NUMBER_VAR", "BOOL_VAR"]:
    value = os.environ.get(var, "NOT_SET")
    print(f"{var}: {value}")

# 使用环境变量
test_val = os.environ.get("TEST_VAR", "default")
number_val = int(os.environ.get("NUMBER_VAR", "0"))
bool_val = os.environ.get("BOOL_VAR", "false").lower() == "true"

print(f"\\nProcessed values:")
print(f"String: {test_val}")
print(f"Number: {number_val}")
print(f"Boolean: {bool_val}")
"""
    
    try:
        result = sandbox.execute_code(
            code=code,
            runtime="python3",
            env_vars=env_vars,
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"标准输出:\n{result.stdout}")
        
        return result.success
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_nodejs_execution():
    """测试Node.js执行"""
    print("\n=== 测试Node.js执行 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_nodejs")
    
    code = """
console.log('Node.js test started');
console.log('Node version:', process.version);

// 简单计算
const numbers = [1, 2, 3, 4, 5];
const sum = numbers.reduce((a, b) => a + b, 0);
const avg = sum / numbers.length;

console.log('Numbers:', numbers);
console.log('Sum:', sum);
console.log('Average:', avg);

// 创建JSON文件
const fs = require('fs');
const result = {
    timestamp: new Date().toISOString(),
    numbers: numbers,
    sum: sum,
    average: avg
};

fs.writeFileSync('nodejs_result.json', JSON.stringify(result, null, 2));
console.log('Result saved to nodejs_result.json');
"""
    
    try:
        result = sandbox.execute_code(
            code=code,
            runtime="node",
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"标准输出:\n{result.stdout}")
        
        if result.stderr:
            print(f"标准错误:\n{result.stderr}")
            
        return result.success
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_bash_execution():
    """测试Bash执行"""
    print("\n=== 测试Bash执行 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_bash")
    
    code = """
echo "Bash test started"
echo "Date: $(date)"
echo "Working directory: $(pwd)"

# 创建目录和文件
mkdir -p test_dir
echo "Hello from bash" > test_dir/hello.txt
echo "Line 2" >> test_dir/hello.txt

# 列出文件
echo "Created files:"
ls -la test_dir/

# 读取文件内容
echo "File content:"
cat test_dir/hello.txt

# 简单计算
echo "Simple calculation:"
echo "5 + 3 = $((5 + 3))"
echo "10 * 2 = $((10 * 2))"

echo "Bash test completed"
"""
    
    try:
        result = sandbox.execute_code(
            code=code,
            runtime="bash",
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"标准输出:\n{result.stdout}")
        
        return result.success
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_error_handling():
    """测试错误处理"""
    print("\n=== 测试错误处理 ===")
    
    config = load_test_config()
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_error")
    
    # 测试语法错误
    bad_code = """
print("This will work")
print(undefined_variable)  # 这会导致错误
print("This won't be reached")
"""
    
    try:
        result = sandbox.execute_code(
            code=bad_code,
            runtime="python3",
            create_filesystem=True
        )
        
        print(f"执行成功: {result.success}")
        print(f"返回码: {result.return_code}")
        print(f"标准输出:\n{result.stdout}")
        print(f"标准错误:\n{result.stderr}")
        
        # 错误处理测试应该返回False（执行失败）
        return not result.success
        
    except Exception as e:
        print(f"测试异常: {e}")
        return True  # 异常也是预期的

def test_resource_limits():
    """测试资源限制"""
    print("\n=== 测试资源限制 ===")
    
    # 使用较短的超时时间进行测试
    config = load_test_config()
    config.max_execution_time = 30  # 30秒超时
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("test_short")
    
    # 测试一个会成功完成的短任务
    short_code = """
import time
print("Starting short operation...")
time.sleep(2)  # 短暂延迟
print("Operation completed successfully")
"""
    
    try:
        start_time = time.time()
        result = sandbox.execute_code(
            code=short_code,
            runtime="python3",
            create_filesystem=True
        )
        execution_time = time.time() - start_time
        
        print(f"执行成功: {result.success}")
        print(f"执行时间: {execution_time:.2f}s")
        print(f"返回码: {result.return_code}")
        
        # 短任务应该成功完成
        return result.success and execution_time < 10
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_strands_integration():
    """测试Strands集成"""
    print("\n=== 测试Strands集成 ===")
    
    try:
        config = load_test_config()
        tools = create_strands_tools(config)
        
        # 测试工具创建
        print(f"创建了 {len(tools)} 个工具")
        for i, tool in enumerate(tools):
            print(f"  {i+1}. {tool.__name__}")
        
        # 测试工具调用
        code_execution_tool = tools[0]
        
        result_json = code_execution_tool(
            code="print('Strands integration test')\nprint(f'Result: {2**10}')",
            runtime="python3",
            task_id="strands_test"
        )
        
        result_dict = json.loads(result_json)
        print(f"工具调用成功: {result_dict['success']}")
        print(f"输出: {result_dict['stdout']}")
        
        return result_dict['success']
        
    except ImportError:
        print("Strands未安装，跳过集成测试")
        return True
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def test_instance_status():
    """测试实例状态检查"""
    print("\n=== 测试实例状态检查 ===")
    
    try:
        config = load_test_config()
        sandbox_env = EC2SandboxEnv(config)
        
        status = sandbox_env.check_instance_status()
        print(f"实例状态: {json.dumps(status, indent=2, default=str)}")
        
        return 'error' not in status
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False

def run_all_tests():
    """运行所有测试"""
    print("开始运行EC2 Sandbox Tool测试套件")
    print("=" * 50)
    
    tests = [
        ("基础代码执行", test_basic_execution),
        ("文件操作", test_file_operations),
        ("环境变量", test_environment_variables),
        ("Node.js执行", test_nodejs_execution),
        ("Bash执行", test_bash_execution),
        ("错误处理", test_error_handling),
        ("资源限制", test_resource_limits),
        ("Strands集成", test_strands_integration),
        ("实例状态", test_instance_status)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n运行测试: {test_name}")
        try:
            success = test_func()
            results.append((test_name, success))
            status = "✓ 通过" if success else "✗ 失败"
            print(f"测试结果: {status}")
        except Exception as e:
            results.append((test_name, False))
            print(f"测试异常: {e}")
    
    # 汇总结果
    print("\n" + "=" * 50)
    print("测试结果汇总:")
    
    passed = 0
    for test_name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"  {test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 个测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！")
    else:
        print("⚠️  部分测试失败，请检查配置和网络连接")

if __name__ == "__main__":
    run_all_tests()
