#!/usr/bin/env python3
"""
EC2 Sandbox 使用示例
演示如何使用基于JSON配置文件的EC2沙箱工具
"""

import os
import json
from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv


def example_basic_usage():
    """基础使用示例"""
    print("=== 基础使用示例 ===")
    
    # 从配置文件创建沙箱环境
    manager = ConfigManager('config.json')
    config = manager.get_config('default')
    
    print(f"使用环境: default")
    print(f"实例ID: {config.instance_id}")
    print(f"区域: {config.region}")
    print(f"认证方式: {manager.get_auth_method('default')}")
    
    # 创建沙箱环境
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("basic_example")
    
    # 简单的Python代码执行
    python_code = """
import sys
import os
from datetime import datetime

print(f"Hello from EC2 Sandbox!")
print(f"Python version: {sys.version}")
print(f"Current time: {datetime.now()}")
print(f"Working directory: {os.getcwd()}")

# 创建一个简单的数据分析
data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
mean = sum(data) / len(data)
print(f"Data: {data}")
print(f"Mean: {mean}")

# 写入结果文件
with open('analysis_result.txt', 'w') as f:
    f.write(f"Analysis Result\\nData: {data}\\nMean: {mean}")

print("Analysis completed!")
"""
    
    result = sandbox.execute_code(
        code=python_code,
        runtime="python3"
    )
    
    print("执行结果:")
    print(f"成功: {result.success}")
    if result.success:
        print(f"输出:\n{result.stdout}")
        print(f"创建的文件: {result.files_created}")
    else:
        print(f"错误: {result.stderr}")


def example_with_files():
    """带文件的使用示例"""
    print("\n=== 带文件的使用示例 ===")
    
    # 创建沙箱环境
    manager = ConfigManager('config.json')
    config = manager.get_config('default')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("file_example")
    
    print(f"使用环境: default")
    print(f"内存限制: {config.max_memory_mb}MB")
    
    # 准备输入文件
    input_files = {
        "data.csv": """name,age,city
Alice,25,New York
Bob,30,San Francisco
Charlie,35,Chicago
Diana,28,Boston""",
        "config.json": json.dumps({
            "analysis_type": "demographic",
            "output_format": "summary",
            "include_charts": True
        }, indent=2)
    }
    
    # 数据分析代码
    analysis_code = """
import json
import csv
from collections import Counter

# 读取配置
with open('config.json', 'r') as f:
    config = json.load(f)

print(f"Analysis type: {config['analysis_type']}")

# 读取数据
people = []
with open('data.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        people.append(row)

print(f"Loaded {len(people)} records")

# 分析数据
ages = [int(person['age']) for person in people]
cities = [person['city'] for person in people]

avg_age = sum(ages) / len(ages)
city_counts = Counter(cities)

print(f"Average age: {avg_age:.1f}")
print(f"City distribution: {dict(city_counts)}")

# 生成报告
report = {
    "total_people": len(people),
    "average_age": round(avg_age, 1),
    "city_distribution": dict(city_counts),
    "age_range": {"min": min(ages), "max": max(ages)}
}

with open('analysis_report.json', 'w') as f:
    json.dump(report, f, indent=2)

print("Report generated: analysis_report.json")
"""
    
    result = sandbox.execute_code(
        code=analysis_code,
        runtime="python3",
        files=input_files
    )
    
    print("执行结果:")
    print(f"成功: {result.success}")
    if result.success:
        print(f"输出:\n{result.stdout}")
        print(f"创建的文件: {result.files_created}")
    else:
        print(f"错误: {result.stderr}")


def example_with_environment():
    """带环境变量的使用示例"""
    print("\n=== 带环境变量的使用示例 ===")
    
    # 创建沙箱环境
    manager = ConfigManager('config.json')
    config = manager.get_config('default')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("env_example")
    
    # 环境变量
    env_vars = {
        "API_KEY": "test-api-key-12345",
        "DEBUG_MODE": "true",
        "MAX_ITEMS": "100",
        "OUTPUT_FORMAT": "json"
    }
    
    # 使用环境变量的代码
    env_code = """
import os

print("Environment Variables:")
for key in ["API_KEY", "DEBUG_MODE", "MAX_ITEMS", "OUTPUT_FORMAT"]:
    value = os.environ.get(key, "Not Set")
    print(f"{key}: {value}")

# 模拟API调用
api_key = os.environ.get("API_KEY")
debug = os.environ.get("DEBUG_MODE", "false").lower() == "true"
max_items = int(os.environ.get("MAX_ITEMS", "10"))

if debug:
    print(f"Debug mode enabled")
    print(f"Using API key: {api_key[:8]}...")
    print(f"Max items: {max_items}")

# 模拟数据处理
data = list(range(1, max_items + 1))
result = {"processed_items": len(data), "sum": sum(data)}

print(f"Processing result: {result}")

# 根据输出格式保存结果
output_format = os.environ.get("OUTPUT_FORMAT", "txt")
if output_format == "json":
    import json
    with open('result.json', 'w') as f:
        json.dump(result, f)
    print("Result saved as JSON")
else:
    with open('result.txt', 'w') as f:
        f.write(str(result))
    print("Result saved as text")
"""
    
    result = sandbox.execute_code(
        code=env_code,
        runtime="python3",
        env_vars=env_vars
    )
    
    print("执行结果:")
    print(f"成功: {result.success}")
    if result.success:
        print(f"输出:\n{result.stdout}")
    else:
        print(f"错误: {result.stderr}")


def example_nodejs():
    """Node.js使用示例"""
    print("\n=== Node.js使用示例 ===")
    
    # 创建沙箱环境
    manager = ConfigManager('config.json')
    config = manager.get_config('default')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance("nodejs_example")
    
    # Node.js代码
    nodejs_code = """
const fs = require('fs');
const path = require('path');

console.log('Node.js Sandbox Example');
console.log('Node version:', process.version);
console.log('Platform:', process.platform);
console.log('Working directory:', process.cwd());

// 创建一些示例数据
const data = {
    timestamp: new Date().toISOString(),
    message: 'Hello from Node.js in EC2 Sandbox!',
    numbers: [1, 2, 3, 4, 5],
    calculation: null
};

// 执行计算
data.calculation = {
    sum: data.numbers.reduce((a, b) => a + b, 0),
    average: data.numbers.reduce((a, b) => a + b, 0) / data.numbers.length,
    max: Math.max(...data.numbers),
    min: Math.min(...data.numbers)
};

console.log('Calculation results:', data.calculation);

// 保存结果
fs.writeFileSync('nodejs_result.json', JSON.stringify(data, null, 2));
console.log('Results saved to nodejs_result.json');

// 读取并验证文件
const savedData = JSON.parse(fs.readFileSync('nodejs_result.json', 'utf8'));
console.log('File verification successful');
console.log('Saved data timestamp:', savedData.timestamp);
"""
    
    result = sandbox.execute_code(
        code=nodejs_code,
        runtime="node"
    )
    
    print("执行结果:")
    print(f"成功: {result.success}")
    if result.success:
        print(f"输出:\n{result.stdout}")
    else:
        print(f"错误: {result.stderr}")



def example_cleanup_and_status():
    """清理和状态检查示例"""
    print("\n=== 清理和状态检查示例 ===")
    
    # 创建沙箱环境
    manager = ConfigManager('config.json')
    config = manager.get_config('default')
    sandbox_env = EC2SandboxEnv(config)
    
    # 检查实例状态
    print("检查EC2实例状态:")
    status = sandbox_env.check_instance_status()
    print(json.dumps(status, indent=2, ensure_ascii=False))
    
    # 手动清理过期任务
    print("\n清理过期任务:")
    try:
        sandbox_env.cleanup_old_tasks(hours=1)  # 清理1小时前的任务
        print("清理完成")
    except Exception as e:
        print(f"清理失败: {e}")
    
    # 演示停止定时器功能
    print("\n停止自动清理定时器:")
    sandbox_env.stop_cleanup_timer()
    print("定时器已停止")


def show_menu():
    """显示交互式菜单"""
    print("\n" + "=" * 60)
    print("🚀 EC2 Sandbox 演示菜单")
    print("=" * 60)
    print("请选择要运行的演示:")
    print()
    print("1. 基础使用示例 - Python代码执行和文件创建")
    print("2. 带文件的使用示例 - 文件输入和数据分析")
    print("3. 带环境变量的使用示例 - 环境变量设置和使用")
    print("4. Node.js使用示例 - Node.js代码执行")
    print("5. 清理和状态检查示例 - 管理功能演示")
    print("6. 运行所有演示")
    print("0. 退出")
    print()


def get_user_choice():
    """获取用户选择"""
    while True:
        try:
            choice = input("请输入选项 (0-6): ").strip()
            if choice in ['0', '1', '2', '3', '4', '5', '6']:
                return int(choice)
            else:
                print("❌ 无效选项，请输入 0-6 之间的数字")
        except KeyboardInterrupt:
            print("\n\n👋 用户取消，退出程序")
            return 0
        except Exception:
            print("❌ 输入错误，请输入 0-6 之间的数字")


def run_demo(choice):
    """运行指定的演示"""
    demos = {
        1: ("基础使用示例", example_basic_usage),
        2: ("带文件的使用示例", example_with_files),
        3: ("带环境变量的使用示例", example_with_environment),
        4: ("Node.js使用示例", example_nodejs),
        5: ("清理和状态检查示例", example_cleanup_and_status),
    }
    
    if choice == 6:
        # 运行所有演示
        print("\n🎬 运行所有演示...")
        for i in range(1, 6):
            demo_name, demo_func = demos[i]
            print(f"\n▶️  正在运行: {demo_name}")
            try:
                demo_func()
                print(f"✅ {demo_name} 完成")
            except Exception as e:
                print(f"❌ {demo_name} 执行出错: {e}")
                import traceback
                traceback.print_exc()
    elif choice in demos:
        # 运行单个演示
        demo_name, demo_func = demos[choice]
        print(f"\n▶️  正在运行: {demo_name}")
        try:
            demo_func()
            print(f"\n✅ {demo_name} 完成")
        except Exception as e:
            print(f"\n❌ {demo_name} 执行出错: {e}")
            import traceback
            traceback.print_exc()


def main():
    """交互式主函数"""
    print("EC2 Sandbox 使用示例")
    print("基于EC2实例的安全代码执行沙箱工具演示")
    
    # 检查配置文件
    if not os.path.exists('config.json'):
        print("\n❌ 配置文件 config.json 不存在")
        print("请先复制 config_template.json 到 config.json 并配置您的实例信息")
        return
    
    # 验证配置
    try:
        manager = ConfigManager('config.json')
        config = manager.get_config('default')
        print(f"\n✅ 配置加载成功")
        print(f"   实例ID: {config.instance_id}")
        print(f"   区域: {config.region}")
        print(f"   认证方式: {manager.get_auth_method('default')}")
    except Exception as e:
        print(f"\n❌ 配置验证失败: {e}")
        print("请检查 config.json 文件的配置")
        return
    
    # 交互式菜单循环
    while True:
        show_menu()
        choice = get_user_choice()
        
        if choice == 0:
            print("\n👋 感谢使用 EC2 Sandbox！")
            break
        
        run_demo(choice)
        
        # 重新返回到交互菜单
        print("↩️  返回主菜单")

if __name__ == "__main__":
    main()
