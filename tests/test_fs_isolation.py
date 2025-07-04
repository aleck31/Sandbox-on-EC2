import os
import sys

# 添加父目录到路径，以便导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv


# 加载配置
manager = ConfigManager('config.json')
config = manager.get_config('default')
config.region = 'ap-northeast-1'

# 创建环境
sandbox_env = EC2SandboxEnv(config)

# 创建两个不同的沙盒实例
sandbox1 = sandbox_env.create_sandbox_instance('user_alice')
sandbox2 = sandbox_env.create_sandbox_instance('user_bob')

# Alice创建文件
result1 = sandbox1.execute_code('''
import os
print(f\"Alice working in: {os.getcwd()}\")
with open(\"alice_secret.txt\", \"w\") as f:
    f.write(\"Alice's secret data\")
print(\"Alice created file:\", os.listdir(\".\"))
''', runtime='python3')

print('=== Alice Result ===')
print(f'Success: {result1.success}')
print(f'Working Dir: {result1.working_directory}')
print(f'Output: {result1.stdout}')

# Bob尝试访问Alice的文件
result2 = sandbox2.execute_code('''
import os
print(f\"Bob working in: {os.getcwd()}\")
print(\"Bob sees files:\", os.listdir(\".\"))
try:
    with open(\"alice_secret.txt\", \"r\") as f:
        print(\"Bob found Alice's secret:\", f.read())
except FileNotFoundError:
    print(\"Bob cannot access Alice's file - Good isolation!\")
''', runtime='python3')

print('\\n=== Bob Result ===')
print(f'Success: {result2.success}')
print(f'Working Dir: {result2.working_directory}')
print(f'Output: {result2.stdout}')
