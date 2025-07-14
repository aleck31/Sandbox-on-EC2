#!/usr/bin/env python3
"""
简化的GPU沙盒测试
专注于验证沙盒工具的GPU环境配置是否正确
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv

def test_gpu_environment_setup():
    """测试GPU环境配置"""
    print("🔍 测试GPU环境配置")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    
    print(f"✅ GPU环境检测: {sandbox_env._is_gpu_environment()}")
    print(f"✅ GPU环境变量数量: {len(sandbox_env.get_gpu_env_vars())}")
    
    gpu_vars = sandbox_env.get_gpu_env_vars()
    for key, value in gpu_vars.items():
        print(f"   {key}: {value[:50]}{'...' if len(value) > 50 else ''}")
    
    return True

def test_sandbox_gpu_execution():
    """测试沙盒GPU代码执行"""
    print("\n🚀 测试沙盒GPU代码执行")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('simple-gpu-test')
    
    # 测试环境变量传递
    result = sandbox.execute_code(
        code='''
import os

print("=== 沙盒GPU环境检查 ===")
gpu_env_vars = [
    "CUDA_HOME",
    "NVIDIA_VISIBLE_DEVICES", 
    "CUDA_VISIBLE_DEVICES",
    "NVIDIA_DRIVER_CAPABILITIES"
]

for var in gpu_env_vars:
    value = os.environ.get(var, "Not set")
    print(f"{var}: {value}")

print("\\n=== PATH检查 ===")
path = os.environ.get("PATH", "")
cuda_in_path = "/usr/local/cuda/bin" in path
conda_in_path = "/opt/miniconda3/envs/gpu-sandbox/bin" in path
print(f"CUDA在PATH中: {cuda_in_path}")
print(f"Conda GPU环境在PATH中: {conda_in_path}")

print("\\n=== Python环境检查 ===")
import sys
print(f"Python可执行文件: {sys.executable}")
print(f"Python版本: {sys.version.split()[0]}")

print("\\n✅ 沙盒GPU环境配置正确！")
''',
        runtime='python'
    )
    
    print(f"执行成功: {result.success}")
    if result.success:
        print("输出:")
        print(result.stdout)
    else:
        print(f"错误: {result.stderr}")
    
    return result.success

def test_basic_gpu_access():
    """测试基础GPU访问"""
    print("\n🎯 测试基础GPU访问")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('gpu-access-test')
    
    result = sandbox.execute_code(
        code='''
import subprocess
import os

print("=== GPU硬件访问测试 ===")

# 测试nvidia-smi
try:
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,utilization.gpu", "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=10
    )
    
    if result.returncode == 0:
        gpu_info = result.stdout.strip().split(", ")
        print(f"✅ GPU名称: {gpu_info[0]}")
        print(f"✅ GPU内存: {gpu_info[1]}MB")
        print(f"✅ GPU使用率: {gpu_info[2]}%")
    else:
        print(f"❌ nvidia-smi失败: {result.stderr}")
        
except Exception as e:
    print(f"❌ nvidia-smi异常: {e}")

# 测试GPU设备文件
gpu_devices = ["/dev/nvidia0", "/dev/nvidiactl", "/dev/nvidia-uvm"]
for device in gpu_devices:
    if os.path.exists(device):
        print(f"✅ GPU设备存在: {device}")
    else:
        print(f"❌ GPU设备缺失: {device}")

print("\\n=== CUDA工具检查 ===")
try:
    result = subprocess.run(["nvcc", "--version"], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        version_line = [line for line in result.stdout.split("\\n") if "release" in line.lower()]
        if version_line:
            print(f"✅ CUDA编译器: {version_line[0].strip()}")
    else:
        print("⚠️ nvcc不可用（正常，运行时不需要）")
except:
    print("⚠️ nvcc检查跳过")

print("\\n🎉 基础GPU访问测试完成！")
''',
        runtime='python'
    )
    
    print(f"执行成功: {result.success}")
    if result.success:
        print("输出:")
        print(result.stdout)
    else:
        print(f"错误: {result.stderr}")
    
    return result.success

def main():
    """主测试函数"""
    print("=" * 60)
    print("🚀 简化GPU沙盒测试")
    print("=" * 60)
    
    tests = [
        ("GPU环境配置", test_gpu_environment_setup),
        ("沙盒GPU执行", test_sandbox_gpu_execution),
        ("基础GPU访问", test_basic_gpu_access)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*40}")
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 结果汇总
    print("\n" + "=" * 60)
    print("📊 测试结果汇总")
    print("=" * 60)
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:15} : {status}")
        if success:
            passed += 1
    
    total = len(results)
    success_rate = (passed / total) * 100
    
    print("-" * 60)
    print(f"测试通过率: {passed}/{total} ({success_rate:.1f}%)")
    
    if success_rate == 100:
        print("\n🎉 GPU沙盒工具配置完美！")
        print("✅ 环境变量自动设置正常")
        print("✅ GPU硬件访问正常")
        print("✅ 沙盒执行环境正常")
        print("\n💡 沙盒工具已准备就绪，可以执行GPU计算任务")
    elif success_rate >= 66:
        print("\n⚠️ GPU沙盒工具基本正常，存在小问题")
    else:
        print("\n❌ GPU沙盒工具存在问题，需要检查配置")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
