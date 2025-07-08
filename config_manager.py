#!/usr/bin/env python3
"""
EC2 Sandbox 配置管理器
基于JSON配置文件的统一配置管理系统
"""

import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
from ec2_sandbox.core import SandboxConfig


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_file: str = "config.json"):
        """
        初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self._configs = {}
        self.load_configs()
    
    def load_configs(self) -> None:
        """加载配置文件"""
        if not self.config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_file}")
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                self._configs = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    def list_environments(self) -> list:
        """列出所有可用的环境配置"""
        # 过滤掉以下划线开头的注释字段
        return [env for env in self._configs.keys() if not env.startswith('_')]
    
    def get_raw_config(self, environment: str = "default") -> Dict[str, Any]:
        """
        获取指定环境的原始配置字典
        
        Args:
            environment: 环境名称
            
        Returns:
            Dict[str, Any]: 原始配置字典
        """
        if environment not in self._configs:
            available = self.list_environments()
            raise ValueError(f"Environment '{environment}' not found. Available: {available}")
        
        return self._configs[environment].copy()
    
    def get_config(self, environment: str = "default") -> SandboxConfig:
        """
        获取指定环境的沙盒配置
        
        Args:
            environment: 环境名称
            
        Returns:
            SandboxConfig: 沙箱配置对象
        """
        # 获取原始配置
        config_dict = self.get_raw_config(environment)
        
        # 从环境变量覆盖配置（如果存在）
        config_dict = self._merge_env_vars(config_dict)
        
        # 验证配置
        self._validate_config(config_dict)
        
        # 创建SandboxConfig对象
        return SandboxConfig(**config_dict)
    
    def _merge_env_vars(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """从环境变量合并配置"""
        env_mappings = {
            'EC2_INSTANCE_ID': 'instance_id',
            'AWS_DEFAULT_REGION': 'region',
            'AWS_PROFILE': 'aws_profile',
            'AWS_ACCESS_KEY_ID': 'access_key_id',
            'AWS_SECRET_ACCESS_KEY': 'secret_access_key',
            'AWS_SESSION_TOKEN': 'session_token',
            'SANDBOX_BASE_DIR': 'base_sandbox_dir',
            'MAX_EXECUTION_TIME': 'max_execution_time',
            'MAX_MEMORY_MB': 'max_memory_mb',
            'CLEANUP_AFTER_HOURS': 'cleanup_after_hours'
        }
        
        for env_var, config_key in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value:
                # 转换数值类型
                if config_key in ['max_execution_time', 'max_memory_mb', 'cleanup_after_hours']:
                    try:
                        config_dict[config_key] = int(env_value)
                    except ValueError:
                        print(f"Warning: Invalid integer value for {env_var}: {env_value}")
                else:
                    config_dict[config_key] = env_value
        
        return config_dict
    
    def _validate_config(self, config_dict: Dict[str, Any]) -> None:
        """验证配置参数"""
        errors = []
        
        # 检查必需参数
        required_fields = ['instance_id', 'region']
        for field in required_fields:
            if not config_dict.get(field):
                errors.append(f"'{field}' is required")
        
        # 检查认证配置
        has_profile = bool(config_dict.get('aws_profile'))
        has_keys = bool(config_dict.get('access_key_id') and config_dict.get('secret_access_key'))
        
        if not (has_profile or has_keys):
            errors.append("Either 'aws_profile' or 'access_key_id'/'secret_access_key' must be provided")
        
        # 检查数值范围
        numeric_fields = {
            'max_execution_time': (30, 3600),  # 30秒到1小时
            'max_memory_mb': (128, 16384),     # 128MB到16GB
            'cleanup_after_hours': (1, 168)    # 1小时到1周
        }
        
        for field, (min_val, max_val) in numeric_fields.items():
            value = config_dict.get(field)
            if value is not None and (not isinstance(value, int) or value < min_val or value > max_val):
                errors.append(f"'{field}' must be an integer between {min_val} and {max_val}")
        
        # 检查运行时
        allowed_runtimes = config_dict.get('allowed_runtimes')
        if allowed_runtimes is not None:  # 只在明确指定时验证
            valid_runtimes = ["python3", "python", "node", "bash", "sh"]
            invalid_runtimes = [rt for rt in allowed_runtimes if rt not in valid_runtimes]
            if invalid_runtimes:
                errors.append(f"Invalid runtimes: {invalid_runtimes}. Valid: {valid_runtimes}")
        
        if errors:
            raise ValueError("Configuration validation failed:\n" + "\n".join(f"  - {error}" for error in errors))
    
    def get_auth_method(self, environment: str = "default") -> str:
        """获取认证方式（用于查询）"""
        config_dict = self._configs.get(environment, {})
        
        if config_dict.get('aws_profile'):
            return "profile"
        elif config_dict.get('access_key_id') and config_dict.get('secret_access_key'):
            return "access_keys" + (" + token" if config_dict.get('session_token') else "")
        else:
            return "unknown"


def main():
    """主函数 - 配置管理器命令行工具"""
    import argparse
    
    parser = argparse.ArgumentParser(description="EC2 Sandbox Configuration Manager")
    parser.add_argument("--config", "-c", default="config.json", help="Configuration file path")
    parser.add_argument("--list", "-l", action="store_true", help="List available environments")
    parser.add_argument("--validate", "-v", help="Validate specific environment configuration")
    parser.add_argument("--show", "-s", help="Show configuration for specific environment")
    parser.add_argument("--auth", "-a", help="Show authentication method for environment")
    
    args = parser.parse_args()
    
    try:
        manager = ConfigManager(args.config)
        
        if args.list:
            environments = manager.list_environments()
            print("Available environments:")
            for env in environments:
                auth_method = manager.get_auth_method(env)
                print(f"  - {env} (auth: {auth_method})")
        
        elif args.validate:
            try:
                config = manager.get_config(args.validate)
                print(f"✅ Configuration '{args.validate}' is valid")
                print(f"   Instance: {config.instance_id}")
                print(f"   Region: {config.region}")
                print(f"   Auth: {manager.get_auth_method(args.validate)}")
            except Exception as e:
                print(f"❌ Configuration '{args.validate}' is invalid: {e}")
        
        elif args.show:
            config = manager.get_config(args.show)
            print(f"Configuration for '{args.show}':")
            print(f"  Instance ID: {config.instance_id}")
            print(f"  Region: {config.region}")
            print(f"  Auth Method: {manager.get_auth_method(args.show)}")
            print(f"  Base Directory: {config.base_sandbox_dir}")
            print(f"  Max Execution Time: {config.max_execution_time}s")
            print(f"  Max Memory: {config.max_memory_mb}MB")
            print(f"  Cleanup After: {config.cleanup_after_hours}h")
            print(f"  Allowed Runtimes: {config.allowed_runtimes}")
        
        elif args.auth:
            auth_method = manager.get_auth_method(args.auth)
            print(f"Authentication method for '{args.auth}': {auth_method}")
        
        else:
            # 默认显示所有环境
            environments = manager.list_environments()
            print(f"Found {len(environments)} environments in {args.config}:")
            for env in environments:
                try:
                    config = manager.get_config(env)
                    auth_method = manager.get_auth_method(env)
                    print(f"  ✅ {env}: {config.instance_id} ({config.region}) - {auth_method}")
                except Exception as e:
                    print(f"  ❌ {env}: Invalid - {e}")
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
