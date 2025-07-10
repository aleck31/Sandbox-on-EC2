#!/usr/bin/env python3
"""
Strands Agent + EC2 Sandbox Demo
演示如何将EC2 Sandbox的所有工具作为Strands Agent的自定义工具使用
"""

from strands import Agent
from strands.models.bedrock import BedrockModel
from config_manager import ConfigManager
from ec2_sandbox.strands_tools import create_strands_tools


SID_DEMO = 'sid-a1b2c3d4e5f'

def create_coding_assistant():
    """创建编程助手Agent"""
    
    # 初始化配置和工具
    print("🔧 初始化EC2沙箱工具...")
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    
    print("🛠️ 创建Strands工具...")
    tools = create_strands_tools(config, SID_DEMO)
    print(f"✅ 创建了 {len(tools)} 个工具")
    
    system_prompt = """
你是一个专业的编程助手，能够帮助用户编写和执行代码。

你拥有以下工具：
1. execute_code_in_sandbox - 在EC2沙箱中执行代码（支持Python、Node.js、Bash等）
2. get_task_files - 获取任务生成的文件内容
3. cleanup_expired_tasks - 清理过期的任务目录
4. check_sandbox_status - 检查EC2沙箱环境状态

当用户提出编程请求时，请：
1. 理解用户需求
2. 选择合适的编程语言和运行时
3. 使用 execute_code_in_sandbox 编写并执行代码
4. 如果需要，使用 get_task_files 获取生成的文件内容
5. 分析结果并向用户解释

你可以处理各种编程任务：数据分析、文件操作、数学计算、Web开发等。
"""
    
    try:
        # 创建 BedrockModel，指定 us-west-2 区域和正确的模型ID
        bedrock_model = BedrockModel(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name="us-west-2",
            temperature=0.1,
            max_tokens=4000
        )
        
        return Agent(
            model=bedrock_model,
            system_prompt=system_prompt,
            tools=tools  # 使用实际的 strands_tools
        )
    except Exception as e:
        print(f"❌ 创建Agent失败: {e}")
        print("请确保：")
        print("1. AWS凭证已正确配置")
        print("2. 在 us-west-2 区域启用了 Claude 3.7 Sonnet 模型访问")
        print("3. 具有 bedrock:InvokeModel 和 bedrock:InvokeModelWithResponseStream 权限")
        return None

def demo_python_execution():
    """演示Python代码执行"""
    print("\n=== Python代码执行演示 ===")
    
    # 初始化工具
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    tools = create_strands_tools(config, SID_DEMO)
    execute_code_in_sandbox = tools[0]  # 第一个工具是代码执行工具
    
    python_code = """
import random
import statistics
import json

# 生成5个随机数
numbers = [random.randint(1, 100) for _ in range(5)]
print(f"随机数列表: {numbers}")

# 计算统计信息
mean = statistics.mean(numbers)
variance = statistics.variance(numbers)
std_dev = statistics.stdev(numbers)

print(f"平均值: {mean:.2f}")
print(f"方差: {variance:.2f}")
print(f"标准差: {std_dev:.2f}")

# 保存结果到文件
result = {
    "numbers": numbers,
    "statistics": {
        "mean": round(mean, 2),
        "variance": round(variance, 2),
        "std_dev": round(std_dev, 2)
    }
}

with open('statistics_result.json', 'w') as f:
    json.dump(result, f, indent=2)

print("结果已保存到 statistics_result.json")
"""
    
    print("🔄 正在执行Python代码...")
    result = execute_code_in_sandbox(
        code=python_code,
        runtime="python3",
        task_id="python_demo"
    )
    print("📋 执行结果:")
    print(result)

def demo_nodejs_execution():
    """演示Node.js代码执行"""
    print("\n=== Node.js代码执行演示 ===")
    
    # 初始化工具
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    tools = create_strands_tools(config, SID_DEMO)
    execute_code_in_sandbox = tools[0]
    
    nodejs_code = """
const fs = require('fs');

console.log('Node.js Web服务器示例');

// 创建简单的HTTP服务器配置
const serverConfig = {
    port: 3000,
    routes: [
        { path: '/', method: 'GET', handler: 'home' },
        { path: '/api/users', method: 'GET', handler: 'getUsers' },
        { path: '/api/users', method: 'POST', handler: 'createUser' }
    ],
    middleware: ['cors', 'bodyParser', 'auth']
};

console.log('服务器配置:');
console.log(JSON.stringify(serverConfig, null, 2));

// 模拟用户数据
const users = [
    { id: 1, name: 'Alice', email: 'alice@example.com' },
    { id: 2, name: 'Bob', email: 'bob@example.com' },
    { id: 3, name: 'Charlie', email: 'charlie@example.com' }
];

// 保存配置和数据
fs.writeFileSync('server_config.json', JSON.stringify(serverConfig, null, 2));
fs.writeFileSync('users_data.json', JSON.stringify(users, null, 2));

console.log('配置文件已生成:');
console.log('- server_config.json');
console.log('- users_data.json');

// 简单的数据处理
const userCount = users.length;
const domains = users.map(u => u.email.split('@')[1]);
const uniqueDomains = [...new Set(domains)];

console.log(`\\n数据统计:`);
console.log(`用户总数: ${userCount}`);
console.log(`邮箱域名: ${uniqueDomains.join(', ')}`);
"""
    
    print("🔄 正在执行Node.js代码...")
    result = execute_code_in_sandbox(
        code=nodejs_code,
        runtime="node",
        task_id="nodejs_demo"
    )
    print("📋 执行结果:")
    print(result)

def demo_file_operations():
    """演示文件操作"""
    print("\n=== 文件操作演示 ===")
    
    # 初始化工具
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    tools = create_strands_tools(config, SID_DEMO)
    get_task_files = tools[1]  # 第二个工具是文件获取工具
    
    print("先执行Python代码生成文件...")
    # 先执行一个简单的Python代码生成文件
    execute_code_in_sandbox = tools[0]
    simple_code = """
import json

data = {
    "message": "Hello from file operations demo!",
    "timestamp": "2025-07-04",
    "items": ["apple", "banana", "cherry"]
}

with open('demo_file.json', 'w') as f:
    json.dump(data, f, indent=2)

print("文件已创建: demo_file.json")
"""
    
    code_result = execute_code_in_sandbox(
        code=simple_code,
        runtime="python3",
        task_id="file_demo"
    )
    print("代码执行结果:")
    print(code_result)
    
    # 从执行结果中提取task_hash
    try:
        import json as json_module
        result_dict = json_module.loads(code_result)
        task_hash = result_dict.get('task_hash')
        
        if task_hash:
            print(f"\n📋 获取生成的文件 (task_hash: {task_hash})...")
            files_result = get_task_files(task_hash=task_hash)
            print("文件内容:")
            print(files_result)
            
            print(f"\n📋 获取特定文件 (demo_file.json)...")
            specific_file = get_task_files(task_hash=task_hash, filename="demo_file.json")
            print("特定文件内容:")
            print(specific_file)
        else:
            print("❌ 无法获取task_hash，跳过文件操作演示")
            
    except Exception as e:
        print(f"❌ 解析执行结果失败: {e}")
        print("跳过文件操作演示")

def demo_status_check():
    """演示状态检查"""
    print("\n=== 状态检查演示 ===")
    
    # 初始化工具
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    tools = create_strands_tools(config, SID_DEMO)
    check_sandbox_status = tools[3]  # 第四个工具是状态检查工具
    
    print("🔄 检查沙箱环境状态...")
    result = check_sandbox_status()
    print("📋 环境状态:")
    print(result)
    """演示直接使用工具"""
    print("\n=== 直接工具使用演示 ===")
    
    # 初始化工具
    config_manager = ConfigManager('config.json')
    config = config_manager.get_sandbox_config('sandbox-default')
    tools = create_strands_tools(config, SID_DEMO)
    
    # 获取各个工具
    execute_code_in_sandbox = tools[0]
    get_task_files = tools[1] 
    cleanup_expired_tasks = tools[2]
    check_sandbox_status = tools[3]
    
    # 1. 执行Python代码
    print("\n📋 1. 执行Python代码演示")
    python_code = """
import random
import json

# 生成销售数据
sales_data = []
months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun']
for month in months:
    sales = random.randint(1000, 5000)
    sales_data.append({'month': month, 'sales': sales})

print("销售数据:")
for data in sales_data:
    print(f"{data['month']}: ${data['sales']}")

# 计算总销售额和平均值
total_sales = sum(item['sales'] for item in sales_data)
avg_sales = total_sales / len(sales_data)

print(f"\\n总销售额: ${total_sales}")
print(f"平均销售额: ${avg_sales:.2f}")

# 保存到文件
with open('sales_report.json', 'w') as f:
    json.dump({
        'data': sales_data,
        'summary': {
            'total': total_sales,
            'average': avg_sales
        }
    }, f, indent=2)

print("报告已保存到 sales_report.json")
"""
    
    result = execute_code_in_sandbox(
        code=python_code,
        runtime="python3",
        task_id="sales_analysis"
    )
    print("执行结果:")
    print(result)
    
    # 2. 获取生成的文件
    print("\n📋 2. 获取生成的文件")
    files_result = get_task_files(task_hash="sales_analysis")
    print("文件内容:")
    print(files_result)
    
    # 3. 检查环境状态
    print("\n📋 3. 检查环境状态")
    status_result = check_sandbox_status()
    print("环境状态:")
    print(status_result)

def demo_agent_interaction():
    """演示Agent交互"""
    print("\n=== Agent交互演示 ===")
    
    agent = create_coding_assistant()
    
    if agent is None:
        print("❌ Agent创建失败，跳过交互演示")
        return
    
    # 预设问题
    questions = [
        "检查当前沙箱环境的状态",
        "生成斐波那契数列的前17项, 计算这17项的平方和",
        "请用Python创建一个简单的数据分析脚本, 分析一组销售数据并生成报告",
    ]
    
    for i, question in enumerate(questions, 1):
        print(f"\n📋 问题 {i}: {question}")
        print("-" * 50)
        
        try:
            response = agent(question)
            # print(f"🤖 Agent响应:\n{response}")
        except Exception as e:
            print(f"❌ 处理问题时出错: {e}")
            import traceback
            traceback.print_exc()

def show_menu():
    """显示交互式菜单"""
    print("\n" + "=" * 60)
    print("🤖 Strands Agent + EC2 Sandbox 演示菜单")
    print("=" * 60)
    print("请选择要运行的演示:")
    print()
    print("1. Python代码执行演示")
    print("2. Node.js代码执行演示")
    print("3. 文件操作演示")
    print("4. 状态检查演示")
    print("5. 运行所有基础演示 (1-4)")
    print("6. Agent交互演示 (需要LLM调用)")
    print("0. 退出")

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
    if choice == 1:
        demo_python_execution()
    elif choice == 2:
        demo_nodejs_execution()
    elif choice == 3:
        demo_file_operations()
    elif choice == 4:
        demo_status_check()
    elif choice == 5:
        print("\n🎬 运行所有基础演示...")
        print("注意：Agent交互演示需要单独运行（选项6）")
        demo_python_execution()
        demo_nodejs_execution()
        demo_file_operations()
        demo_status_check()
        print("\n✅ 所有基础演示完成！")
    elif choice == 6:
        demo_agent_interaction()

def main():
    """主函数"""
    print("🚀 Strands Agent + EC2 Sandbox 演示")
    print("演示如何将EC2 Sandbox的所有工具作为Strands Agent的自定义工具使用")
    
    # 检查配置
    try:
        config_manager = ConfigManager('config.json')
        config = config_manager.get_sandbox_config('sandbox-default')
        print(f"\n✅ 配置加载成功")
        print(f"   实例ID: {config.instance_id}")
        print(f"   区域: {config.region}")
    except Exception as e:
        print(f"\n❌ 配置加载失败: {e}")
        return
    
    # 交互式菜单循环
    try:
        while True:
            show_menu()
            choice = get_user_choice()
            
            if choice == 0:
                print("\n👋 感谢使用 Strands Agent + EC2 Sandbox！")
                break
            
            run_demo(choice)
            
            # 重新返回到交互菜单
            print("↩️  返回主菜单")
            
    except Exception as e:
        print(f"❌ 演示过程中出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
