#!/bin/bash

# GPU EC2 Sandbox - 用户数据脚本
# 基于 Deep Learning Base OSS Nvidia Driver GPU AMI (Ubuntu 22.04)
# 该AMI已预装: NVIDIA驱动、CUDA 12.4-12.8、Docker、AWS CLI、Python 3.10

set -e

# 日志文件
LOG_FILE="/var/log/gpu-sandbox-init.log"
exec > >(tee -a $LOG_FILE)
exec 2>&1

echo "=== GPU Sandbox 初始化开始 $(date) ==="

# 设置CUDA环境变量 (AMI预装了多个CUDA版本，默认使用12.8)
echo "设置CUDA环境变量..."
export CUDA_HOME=/usr/local/cuda
export PATH="/usr/local/cuda/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:/usr/local/cuda/extras/CUPTI/lib64:$LD_LIBRARY_PATH"

# 持久化CUDA环境变量到系统
echo "持久化CUDA环境变量..."
cat >> /etc/environment << EOF
CUDA_HOME=/usr/local/cuda
EOF

# 为所有用户设置CUDA PATH
cat > /etc/profile.d/cuda.sh << EOF
#!/bin/bash
# CUDA Environment Variables
export CUDA_HOME=/usr/local/cuda
export PATH="/usr/local/cuda/bin:\$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda/lib64:/usr/local/cuda/extras/CUPTI/lib64:\$LD_LIBRARY_PATH"
EOF
chmod +x /etc/profile.d/cuda.sh

# 验证预装组件
echo "验证预装的GPU组件..."
nvidia-smi
nvcc --version
python3 --version

# 更新系统包
echo "更新系统包..."
apt-get update -y

# 安装额外的实用工具
echo "安装额外工具..."
apt-get install -y \
    htop \
    tree \
    vim \
    jq \
    screen \
    tmux \
    ffmpeg

# 升级pip
echo "升级pip..."
python3 -m pip install --upgrade pip

# 安装GPU加速库 (直接使用系统Python)
echo "安装PyTorch (CUDA 12.1)..."
python3 -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo "安装GPU计算库..."
python3 -m pip install \
    cupy-cuda12x \
    numba

echo "安装数据科学库..."
python3 -m pip install \
    pandas \
    numpy \
    matplotlib \
    seaborn \
    plotly \
    scipy \
    scikit-learn \
    opencv-python

# 创建沙盒目录
echo "创建沙盒目录结构..."
mkdir -p /opt/sandbox/{tasks,logs,temp}
chmod 755 /opt/sandbox
chmod 777 /opt/sandbox/tasks
chmod 777 /opt/sandbox/logs
chmod 777 /opt/sandbox/temp

# 设置用户权限
echo "设置用户权限..."
if id "ubuntu" &>/dev/null; then
    chown -R ubuntu:ubuntu /opt/sandbox
    usermod -aG docker ubuntu 2>/dev/null || true
fi

echo "=== GPU Sandbox 初始化完成 $(date) ==="
echo "📋 初始化摘要:"
echo "   ✅ 使用预装的NVIDIA驱动和CUDA 12.8"
echo "   ✅ 使用系统Python环境"
echo "   ✅ 安装了PyTorch、CuPy、数据科学库"
echo "   ✅ 配置了全局CUDA环境变量"
echo ""
echo "📁 重要文件:"
echo "   日志: $LOG_FILE"
echo "   沙盒目录: /opt/sandbox"
echo ""
echo "🚀 环境已就绪，可直接使用python3命令"
