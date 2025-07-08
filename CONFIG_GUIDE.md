# EC2 Sandbox 配置指南

## 配置文件结构

### 基本配置格式

```json
{
  "environment_name": {
    "instance_id": "i-1234567890abcdef0",
    "region": "us-east-1",
    "aws_profile": "default",
    "base_sandbox_dir": "/opt/sandbox",
    "max_execution_time": 300,
    "max_memory_mb": 1024,
    "cleanup_after_hours": 24
  }
}
```

### 配置参数详解

| 参数 | 类型 | 必需 | 默认值 | 范围 | 说明 |
|------|------|------|--------|------|------|
| `instance_id` | string | ✅ | - | - | EC2实例ID |
| `region` | string | ✅ | - | - | AWS区域 |
| `aws_profile` | string | * | - | - | AWS配置文件名 |
| `access_key_id` | string | * | - | - | AWS访问密钥ID |
| `secret_access_key` | string | * | - | - | AWS秘密访问密钥 |
| `session_token` | string | - | - | - | 临时凭证token |
| `base_sandbox_dir` | string | - | `/opt/sandbox` | - | 沙盒基础目录 |
| `max_execution_time` | int | - | `300` | 30-3600 | 最大执行时间(秒) |
| `max_memory_mb` | int | - | `1024` | 128-8192 | 最大内存(MB) |
| `cleanup_after_hours` | int | - | `24` | 1-168 | 清理时间(小时) |
| `allowed_runtimes` | array | - | 自动设置 | - | 允许的运行时 |

*认证参数：必须提供 `aws_profile` 或 `access_key_id`/`secret_access_key`

## 认证配置

### 方式1：AWS Profile（推荐）
```json
{
  "aws_profile": "default"
}
```

### 方式2：访问密钥
```json
{
  "access_key_id": "AKIAIOSFODNN7EXAMPLE",
  "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}
```

### 方式3：临时凭证（STS）
```json
{
  "access_key_id": "ASIAIOSFODNN7EXAMPLE",
  "secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
  "session_token": "AQoDYXdzEJr...<remainder of security token>"
}
```

## 多环境配置

### 环境配置示例

```json
{
  "development": {
    "instance_id": "i-dev123456789",
    "region": "us-east-1",
    "aws_profile": "dev",
    "max_execution_time": 60,
    "max_memory_mb": 512,
    "cleanup_after_hours": 1
  },
  "production": {
    "instance_id": "i-prod123456789",
    "region": "us-west-2",
    "aws_profile": "prod",
    "max_execution_time": 900,
    "max_memory_mb": 4096,
    "cleanup_after_hours": 48
  },
  "data-science": {
    "instance_id": "i-ds123456789",
    "region": "us-east-1",
    "aws_profile": "data",
    "max_execution_time": 1800,
    "max_memory_mb": 8192,
    "cleanup_after_hours": 72
  }
}
```

## 环境变量覆盖

### 支持的环境变量

| 环境变量 | 配置参数 | 示例 |
|----------|----------|------|
| `EC2_INSTANCE_ID` | `instance_id` | `i-1234567890abcdef0` |
| `AWS_DEFAULT_REGION` | `region` | `us-east-1` |
| `AWS_PROFILE` | `aws_profile` | `default` |
| `AWS_ACCESS_KEY_ID` | `access_key_id` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `secret_access_key` | `wJal...` |
| `AWS_SESSION_TOKEN` | `session_token` | `AQoD...` |
| `SANDBOX_BASE_DIR` | `base_sandbox_dir` | `/opt/sandbox` |
| `MAX_EXECUTION_TIME` | `max_execution_time` | `600` |
| `MAX_MEMORY_MB` | `max_memory_mb` | `2048` |
| `CLEANUP_AFTER_HOURS` | `cleanup_after_hours` | `12` |

### 使用示例

```bash
# 临时覆盖配置
export EC2_INSTANCE_ID=i-override123
export MAX_EXECUTION_TIME=600
uv run python your_script.py

# 或在脚本中设置
EC2_INSTANCE_ID=i-override123 MAX_EXECUTION_TIME=600 uv run python your_script.py
```

## 配置验证

### 使用配置管理器验证

```bash
# 验证特定环境
python config_manager.py --validate development

# 查看配置详情
python config_manager.py --show production

# 检查认证方式
python config_manager.py --auth default

# 列出所有环境
python config_manager.py --list
```

## 配置最佳实践

### 1. 安全配置

```bash
# 不要将敏感信息提交到版本控制
echo "config.json" >> .gitignore
echo "config_*.json" >> .gitignore

# 使用模板创建配置
cp config.json.template config.json
```

### 2. 环境分离

```json
{
  "dev": {
    "instance_id": "i-dev123",
    "max_execution_time": 60,
    "cleanup_after_hours": 1
  },
  "staging": {
    "instance_id": "i-staging123",
    "max_execution_time": 300,
    "cleanup_after_hours": 12
  },
  "prod": {
    "instance_id": "i-prod123",
    "max_execution_time": 900,
    "cleanup_after_hours": 48
  }
}
```

### 3. 资源配置建议

| 用途 | 执行时间 | 内存 | 清理间隔 |
|------|----------|------|----------|
| 开发测试 | 60s | 512MB | 1小时 |
| 教育培训 | 120s | 256MB | 2小时 |
| 数据科学 | 1800s | 8192MB | 72小时 |
| 生产环境 | 900s | 4096MB | 48小时 |

## 故障排除

### 配置错误诊断

```bash
# 1. 检查配置文件语法
python -m json.tool config.json

# 2. 验证配置参数
python config_manager.py --validate default

# 3. 查看实际加载的配置
python config_manager.py --show default

# 4. 检查认证配置
python config_manager.py --auth default
```

### 常见配置问题

#### 1. 认证配置错误
```
Either 'aws_profile' or 'access_key_id'/'secret_access_key' must be provided
```
**解决**: 确保提供了有效的认证配置

#### 2. 参数范围错误
```
'max_execution_time' must be an integer between 30 and 3600
```
**解决**: 调整参数值到有效范围内

#### 3. JSON格式错误
```
Invalid JSON in configuration file
```
**解决**: 检查JSON语法，移除注释，确保引号配对

#### 4. 环境变量冲突
**问题**: 配置被意外覆盖
**解决**: 检查环境变量设置
```bash
env | grep -E "(AWS_|EC2_|SANDBOX_|MAX_|CLEANUP_)"
```

#### 5. 模板命令已移除
```
python config_manager.py --template
```
**解决**: 直接复制配置模板文件
```bash
cp config.json.template config.json
```

## 配置模板参考

参考项目根目录下的 `config.json.template` 文件获取完整的配置模板和示例。
