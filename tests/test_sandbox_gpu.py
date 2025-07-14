#!/usr/bin/env python3
"""
GPU沙盒环境测试示例
测试各种GPU计算场景，验证沙盒环境是否正常工作
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv

def test_basic_gpu_detection():
    """测试1: 基础GPU环境检测"""
    print("🔍 测试1: 基础GPU环境检测")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('gpu-basic-test')
    
    result = sandbox.execute_code(
        code='''
import os
import subprocess

print("=== GPU环境检测 ===")
print(f"CUDA_HOME: {os.environ.get('CUDA_HOME', 'Not set')}")
print(f"NVIDIA_VISIBLE_DEVICES: {os.environ.get('NVIDIA_VISIBLE_DEVICES', 'Not set')}")
print(f"PATH包含CUDA: {'/usr/local/cuda/bin' in os.environ.get('PATH', '')}")

# 检查nvidia-smi
try:
    result = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,driver_version', 
                           '--format=csv,noheader,nounits'], 
                          capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        gpu_info = result.stdout.strip().split(', ')
        print(f"GPU名称: {gpu_info[0]}")
        print(f"GPU内存: {gpu_info[1]}MB")
        print(f"驱动版本: {gpu_info[2]}")
        print("✅ GPU硬件检测成功")
    else:
        print("❌ nvidia-smi执行失败")
except Exception as e:
    print(f"❌ GPU检测异常: {e}")
''',
        runtime='python'
    )
    
    print(f"执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    if not result.success:
        print(f"错误信息: {result.stderr}")
    return result.success

def test_pytorch_gpu():
    """测试2: PyTorch GPU计算"""
    print("\n🧠 测试2: PyTorch GPU深度学习")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('pytorch-gpu-test')
    
    result = sandbox.execute_code(
        code='''
import torch
import torch.nn as nn
import torch.optim as optim
import time

print("=== PyTorch GPU测试 ===")
print(f"PyTorch版本: {torch.__version__}")
print(f"CUDA可用: {torch.cuda.is_available()}")

if not torch.cuda.is_available():
    print("❌ CUDA不可用，跳过GPU测试")
    exit(1)

print(f"GPU设备数量: {torch.cuda.device_count()}")
print(f"当前GPU: {torch.cuda.get_device_name(0)}")

# 创建一个简单的神经网络
class SimpleNet(nn.Module):
    def __init__(self):
        super(SimpleNet, self).__init__()
        self.fc1 = nn.Linear(784, 256)
        self.fc2 = nn.Linear(256, 128)
        self.fc3 = nn.Linear(128, 10)
        self.relu = nn.ReLU()
        
    def forward(self, x):
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.fc3(x)
        return x

# 移动模型到GPU
device = torch.device('cuda:0')
model = SimpleNet().to(device)
criterion = nn.CrossEntropyLoss()
optimizer = optim.Adam(model.parameters(), lr=0.001)

print("✅ 模型已移动到GPU")

# 创建模拟数据
batch_size = 64
input_data = torch.randn(batch_size, 784).to(device)
target = torch.randint(0, 10, (batch_size,)).to(device)

print("✅ 数据已移动到GPU")

# 训练几个步骤
print("开始GPU训练...")
start_time = time.time()

for epoch in range(5):
    optimizer.zero_grad()
    output = model(input_data)
    loss = criterion(output, target)
    loss.backward()
    optimizer.step()
    
    if epoch % 2 == 0:
        print(f"Epoch {epoch}: Loss = {loss.item():.4f}")

end_time = time.time()
print(f"✅ GPU训练完成，耗时: {end_time - start_time:.2f}秒")

# 测试推理
model.eval()
with torch.no_grad():
    test_input = torch.randn(10, 784).to(device)
    predictions = model(test_input)
    predicted_classes = torch.argmax(predictions, dim=1)
    print(f"✅ GPU推理完成，预测结果: {predicted_classes.cpu().numpy()}")

print("🎉 PyTorch GPU测试成功！")
''',
        runtime='python'
    )
    
    print(f"执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    if not result.success:
        print(f"错误信息: {result.stderr}")
    return result.success

def test_gpu_matrix_operations():
    """测试3: GPU矩阵运算性能"""
    print("\n🔢 测试3: GPU矩阵运算性能")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('matrix-gpu-test')
    
    result = sandbox.execute_code(
        code='''
import torch
import time
import numpy as np

print("=== GPU矩阵运算性能测试 ===")

if not torch.cuda.is_available():
    print("❌ CUDA不可用")
    exit(1)

# 设置矩阵大小
matrix_size = 2048
device = torch.device('cuda:0')

print(f"矩阵大小: {matrix_size}x{matrix_size}")

# CPU矩阵运算
print("\\n--- CPU矩阵运算 ---")
cpu_a = torch.randn(matrix_size, matrix_size)
cpu_b = torch.randn(matrix_size, matrix_size)

start_time = time.time()
cpu_result = torch.mm(cpu_a, cpu_b)
cpu_time = time.time() - start_time
print(f"CPU矩阵乘法耗时: {cpu_time:.3f}秒")

# GPU矩阵运算
print("\\n--- GPU矩阵运算 ---")
gpu_a = cpu_a.to(device)
gpu_b = cpu_b.to(device)

# 预热GPU
_ = torch.mm(gpu_a, gpu_b)
torch.cuda.synchronize()

start_time = time.time()
gpu_result = torch.mm(gpu_a, gpu_b)
torch.cuda.synchronize()  # 确保GPU计算完成
gpu_time = time.time() - start_time

print(f"GPU矩阵乘法耗时: {gpu_time:.3f}秒")
print(f"GPU加速比: {cpu_time/gpu_time:.1f}x")

# 验证结果一致性
cpu_result_check = gpu_result.cpu()
max_diff = torch.max(torch.abs(cpu_result - cpu_result_check)).item()
print(f"CPU/GPU结果最大差异: {max_diff:.2e}")

if max_diff < 1e-4:
    print("✅ CPU和GPU计算结果一致")
else:
    print("⚠️ CPU和GPU计算结果存在差异")

# GPU内存使用情况
if hasattr(torch.cuda, 'memory_allocated'):
    memory_allocated = torch.cuda.memory_allocated(device) / 1024**2
    memory_reserved = torch.cuda.memory_reserved(device) / 1024**2
    print(f"\\nGPU内存使用: {memory_allocated:.1f}MB (已分配)")
    print(f"GPU内存保留: {memory_reserved:.1f}MB (已保留)")

print("🎉 GPU矩阵运算测试成功！")
''',
        runtime='python'
    )
    
    print(f"执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    if not result.success:
        print(f"错误信息: {result.stderr}")
    return result.success

def test_gpu_image_processing():
    """测试4: GPU图像处理"""
    print("\n🖼️ 测试4: GPU图像处理")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('image-gpu-test')
    
    result = sandbox.execute_code(
        code='''
import torch
import torch.nn.functional as F
import time

print("=== GPU图像处理测试 ===")

if not torch.cuda.is_available():
    print("❌ CUDA不可用")
    exit(1)

device = torch.device('cuda:0')

# 创建模拟图像数据 (batch_size, channels, height, width)
batch_size = 32
channels = 3
height, width = 224, 224

print(f"图像批次: {batch_size}张")
print(f"图像尺寸: {channels}x{height}x{width}")

# 生成随机图像数据
images = torch.randn(batch_size, channels, height, width).to(device)
print("✅ 图像数据已移动到GPU")

# 图像处理操作
print("\\n--- GPU图像处理操作 ---")

start_time = time.time()

# 1. 图像缩放
resized = F.interpolate(images, size=(112, 112), mode='bilinear', align_corners=False)
print(f"✅ 图像缩放: {images.shape} -> {resized.shape}")

# 2. 图像卷积 (模拟边缘检测)
sobel_x = torch.tensor([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=torch.float32).to(device)
sobel_x = sobel_x.view(1, 1, 3, 3).repeat(channels, 1, 1, 1)

edges = F.conv2d(images, sobel_x, padding=1, groups=channels)
print(f"✅ 边缘检测卷积: {edges.shape}")

# 3. 图像池化
pooled = F.max_pool2d(images, kernel_size=2, stride=2)
print(f"✅ 最大池化: {images.shape} -> {pooled.shape}")

# 4. 图像归一化
normalized = F.normalize(images, p=2, dim=1)
print(f"✅ 图像归一化: {normalized.shape}")

# 5. 批量图像变换
flipped = torch.flip(images, dims=[3])  # 水平翻转
rotated = torch.rot90(images, k=1, dims=[2, 3])  # 旋转90度
print(f"✅ 图像变换: 翻转和旋转")

torch.cuda.synchronize()
processing_time = time.time() - start_time

print(f"\\nGPU图像处理总耗时: {processing_time:.3f}秒")
print(f"平均每张图像: {processing_time/batch_size*1000:.1f}毫秒")

# 内存使用情况
memory_used = torch.cuda.memory_allocated(device) / 1024**2
print(f"GPU内存使用: {memory_used:.1f}MB")

print("🎉 GPU图像处理测试成功！")
''',
        runtime='python'
    )
    
    print(f"执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    if not result.success:
        print(f"错误信息: {result.stderr}")
    return result.success

def test_gpu_memory_management():
    """测试5: GPU内存管理"""
    print("\n💾 测试5: GPU内存管理")
    
    manager = ConfigManager('config.json')
    config = manager.get_sandbox_config('sandbox-gpu')
    sandbox_env = EC2SandboxEnv(config)
    sandbox = sandbox_env.create_sandbox_instance('memory-gpu-test')
    
    result = sandbox.execute_code(
        code='''
import torch
import gc

print("=== GPU内存管理测试 ===")

if not torch.cuda.is_available():
    print("❌ CUDA不可用")
    exit(1)

device = torch.device('cuda:0')

def get_gpu_memory():
    """获取GPU内存使用情况"""
    allocated = torch.cuda.memory_allocated(device) / 1024**2
    reserved = torch.cuda.memory_reserved(device) / 1024**2
    return allocated, reserved

# 初始内存状态
torch.cuda.empty_cache()
initial_allocated, initial_reserved = get_gpu_memory()
print(f"初始内存 - 已分配: {initial_allocated:.1f}MB, 已保留: {initial_reserved:.1f}MB")

# 分配大量GPU内存
print("\\n--- 分配GPU内存 ---")
tensors = []
for i in range(5):
    size = 1024 * (i + 1)  # 逐渐增大
    tensor = torch.randn(size, size).to(device)
    tensors.append(tensor)
    
    allocated, reserved = get_gpu_memory()
    print(f"分配 {size}x{size} 张量 - 已分配: {allocated:.1f}MB, 已保留: {reserved:.1f}MB")

max_allocated, max_reserved = get_gpu_memory()
print(f"\\n最大内存使用 - 已分配: {max_allocated:.1f}MB, 已保留: {max_reserved:.1f}MB")

# 释放部分内存
print("\\n--- 释放GPU内存 ---")
del tensors[2:4]  # 删除中间两个张量
gc.collect()
torch.cuda.empty_cache()

after_partial_free = get_gpu_memory()
print(f"部分释放后 - 已分配: {after_partial_free[0]:.1f}MB, 已保留: {after_partial_free[1]:.1f}MB")

# 释放所有内存
del tensors
gc.collect()
torch.cuda.empty_cache()

final_allocated, final_reserved = get_gpu_memory()
print(f"完全释放后 - 已分配: {final_allocated:.1f}MB, 已保留: {final_reserved:.1f}MB")

# 内存管理验证
memory_freed = max_allocated - final_allocated
print(f"\\n内存释放量: {memory_freed:.1f}MB")

if final_allocated <= initial_allocated + 10:  # 允许10MB误差
    print("✅ GPU内存管理正常")
else:
    print("⚠️ 可能存在内存泄漏")

# GPU设备信息
props = torch.cuda.get_device_properties(device)
print(f"\\nGPU设备信息:")
print(f"  名称: {props.name}")
print(f"  总内存: {props.total_memory / 1024**3:.1f}GB")
print(f"  多处理器数量: {props.multi_processor_count}")
print(f"  CUDA计算能力: {props.major}.{props.minor}")

print("🎉 GPU内存管理测试成功！")
''',
        runtime='python'
    )
    
    print(f"执行结果: {'✅ 成功' if result.success else '❌ 失败'}")
    if not result.success:
        print(f"错误信息: {result.stderr}")
    return result.success

def main():
    """主测试函数"""
    print("=" * 70)
    print("🚀 GPU沙盒环境综合测试")
    print("=" * 70)
    
    tests = [
        ("基础GPU环境检测", test_basic_gpu_detection),
        ("PyTorch GPU深度学习", test_pytorch_gpu),
        ("GPU矩阵运算性能", test_gpu_matrix_operations),
        ("GPU图像处理", test_gpu_image_processing),
        ("GPU内存管理", test_gpu_memory_management)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*50}")
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name}测试异常: {e}")
            results.append((test_name, False))
    
    # 测试结果汇总
    print("\n" + "=" * 70)
    print("📊 GPU沙盒环境测试结果汇总")
    print("=" * 70)
    
    passed = 0
    for test_name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{test_name:20} : {status}")
        if success:
            passed += 1
    
    total = len(results)
    success_rate = (passed / total) * 100
    
    print("-" * 70)
    print(f"测试通过率: {passed}/{total} ({success_rate:.1f}%)")
    
    if success_rate >= 80:
        print("\n🎉 恭喜！GPU沙盒环境运行正常！")
        print("💡 环境已准备就绪，可以进行GPU加速的机器学习和科学计算任务")
    elif success_rate >= 60:
        print("\n⚠️ GPU沙盒环境基本可用，但存在部分问题")
        print("💡 建议检查失败的测试项目")
    else:
        print("\n❌ GPU沙盒环境存在严重问题")
        print("💡 建议检查GPU驱动、CUDA安装和PyTorch配置")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
