import os
import sys
import random

# 添加父目录到路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv


def main():
    print("=== EC2 Sandbox File Isolation Test ===")
    
    try:
        # 加载配置
        manager = ConfigManager('config.json')
        config = manager.get_sandbox_config('sandbox-default')
        
        # 创建环境
        sandbox_env = EC2SandboxEnv(config)
        
        # 创建两个不同的沙盒实例
        alice_task_id = f'alice_{random.randint(1000, 9999)}'
        bob_task_id = f'bob_{random.randint(1000, 9999)}'
        
        sandbox1 = sandbox_env.create_sandbox_instance(alice_task_id)
        sandbox2 = sandbox_env.create_sandbox_instance(bob_task_id)
        
        print(f"Alice task ID: {alice_task_id}")
        print(f"Bob task ID: {bob_task_id}")
        
        # Alice创建文件
        print("\n=== Alice Creating File ===")
        result1 = sandbox1.execute_code('''
import os
print(f"Alice working in: {os.getcwd()}")
with open("alice_secret.txt", "w") as f:
    f.write("Alice's secret data")
print("Alice created file:", os.listdir("."))
''', runtime='python')
        
        print('=== Alice Result ===')
        print(f'Success: {result1.success}')
        print(f'Return Code: {result1.return_code}')
        print(f'Working Dir: {result1.working_directory}')
        print(f'Task Hash: {result1.task_hash}')
        print(f'Output: {result1.stdout}')
        if result1.stderr:
            print(f'Errors: {result1.stderr}')
        if result1.error_message:
            print(f'Error Message: {result1.error_message}')
        
        # Bob尝试访问Alice的文件
        print("\n=== Bob Trying to Access Alice's File ===")
        result2 = sandbox2.execute_code('''
import os
print(f"Bob working in: {os.getcwd()}")
print("Bob sees files:", os.listdir("."))
try:
    with open("alice_secret.txt", "r") as f:
        print("Bob found Alice's secret:", f.read())
except FileNotFoundError:
    print("Bob cannot access Alice's file - Good isolation!")
''', runtime='python')
        
        print('=== Bob Result ===')
        print(f'Success: {result2.success}')
        print(f'Return Code: {result2.return_code}')
        print(f'Working Dir: {result2.working_directory}')
        print(f'Task Hash: {result2.task_hash}')
        print(f'Output: {result2.stdout}')
        if result2.stderr:
            print(f'Errors: {result2.stderr}')
        if result2.error_message:
            print(f'Error Message: {result2.error_message}')
        
        # 验证隔离效果
        print("\n=== Isolation Test Results ===")
        if result1.success and result2.success:
            if "Bob cannot access Alice's file" in result2.stdout:
                print("✅ File isolation test PASSED!")
            else:
                print("❌ File isolation test FAILED - Bob can access Alice's file!")
        else:
            print("❌ Test execution failed")
            
    except Exception as e:
        print(f"Test failed with exception: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
