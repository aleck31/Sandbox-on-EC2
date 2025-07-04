#!/bin/bash
exec > >(tee /var/log/sandbox-setup.log) 2>&1
echo "=== EC2 Sandbox Setup Started at $(date) ==="

echo "📦 Updating system packages..."
apt-get update -y

echo "🔧 Installing essential development tools..."
apt-get install -y \
    python3 \
    python3-dev \
    nodejs \
    npm \
    curl \
    wget \
    unzip \
    git

echo "📊 Installing core data analysis libraries..."
apt-get install -y \
    python3-pandas \
    python3-numpy \
    python3-matplotlib \
    python3-plotly \
    python3-scipy \
    python3-requests \
    python3-openpyxl \
    python3-bs4 \
    python3-lxml

echo "🐍 Setting up python symlink..."
ln -sf /usr/bin/python3 /usr/bin/python

echo "☁️ Installing AWS CLI v2..."
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install
rm -rf aws awscliv2.zip

echo "📁 Creating sandbox directories..."
mkdir -p /opt/sandbox
chmod 755 /opt/sandbox

echo "✅ Verifying installations..."
echo "Python version: $(python3 --version)"
echo "Node.js version: $(node --version)"
echo "NPM version: $(npm --version)"
echo "AWS CLI version: $(aws --version)"

echo "🧪 Testing core data analysis libraries..."
python3 -c "
libraries = ['pandas', 'numpy', 'matplotlib', 'plotly', 'scipy', 'requests', 'openpyxl', 'bs4', 'lxml']
success = 0
for lib in libraries:
    try:
        __import__(lib)
        print(f'✅ {lib} - OK')
        success += 1
    except ImportError as e:
        print(f'❌ {lib} - FAILED: {e}')
print(f'\\n📊 Data analysis libraries: {success}/{len(libraries)} working')
"

echo "🧪 Testing Node.js..."
node -e "console.log('✅ Node.js - OK')" || echo "❌ Node.js - FAILED"

echo "=== EC2 Sandbox Setup Completed at $(date) ==="
echo "🎉 Setup completed successfully!"