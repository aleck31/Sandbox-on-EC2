#!/usr/bin/env python3
"""
EC2 Sandbox 核心功能
基于EC2实例的沙箱环境管理 - 核心实现
"""

import base64
import threading
from typing import Dict, Any, Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .sandbox import SandboxInstance
from dataclasses import dataclass
from .utils import logger, is_safe_filename, create_aws_client


@dataclass
class SandboxConfig:
    """沙盒基础环境配置"""
    region: str
    instance_id: str
    aws_profile: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    session_token: Optional[str] = None
    base_sandbox_dir: str = "/opt/sandbox"
    max_execution_time: int = 300  # 5分钟
    max_memory_mb: int = 1024
    cleanup_after_hours: int = 24
    allowed_runtimes: Optional[List[str]] = None
    timestamp: Optional[str] = None  # 配置更新时间

    def __post_init__(self):
        if self.allowed_runtimes is None:
            self.allowed_runtimes = ["python3", "python", "node", "bash", "sh"]


class EC2SandboxEnv:
    """EC2沙盒环境 - 单例, 对应一个EC2实例, 负责基础设施管理"""
    
    _instances = {}  # 按配置缓存环境实例
    
    def __new__(cls, config: SandboxConfig):
        # 基于实例ID创建唯一的环境实例
        instance_key = f"{config.instance_id}_{config.region}"
        
        if instance_key not in cls._instances:
            logger.info(f"初始化EC2沙盒环境: {config.instance_id}")
            instance = super().__new__(cls)
            cls._instances[instance_key] = instance
        else:
            logger.debug(f"复用现有EC2沙盒环境: {config.instance_id}")
            
        return cls._instances[instance_key]
    
    def __init__(self, config: SandboxConfig):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
            
        self.config = config
        self.ec2_client = self._create_ec2_client()
        self.ssm_client = self._create_ssm_client()
        self._ensure_base_directory()
        
        # 初始化清理定时器
        self._cleanup_timer = None
        self._cleanup_interval_hours = 1.0  # 默认每小时清理一次
        self._start_cleanup_timer()
        
        self._initialized = True
        logger.info(f"EC2沙盒环境初始化完成: {config.instance_id}")
    
    def create_sandbox_instance(self, task_id: Optional[str] = None) -> 'SandboxInstance':
        """在环境中创建一个沙盒实例"""
        from .sandbox import SandboxInstance
        return SandboxInstance(self, task_id)
        
    def _create_ec2_client(self):
        """创建EC2客户端"""
        return create_aws_client(
            service='ec2',
            region=self.config.region,
            aws_profile=self.config.aws_profile,
            access_key_id=self.config.access_key_id,
            secret_access_key=self.config.secret_access_key,
            session_token=self.config.session_token
        )
    
    def _create_ssm_client(self):
        """创建SSM客户端用于远程执行"""
        return create_aws_client(
            service='ssm',
            region=self.config.region,
            aws_profile=self.config.aws_profile,
            access_key_id=self.config.access_key_id,
            secret_access_key=self.config.secret_access_key,
            session_token=self.config.session_token
        )
    
    def _ensure_base_directory(self):
        """确保基础沙箱目录存在"""
        try:
            command = f"sudo mkdir -p {self.config.base_sandbox_dir} && sudo chmod 755 {self.config.base_sandbox_dir}"
            self._execute_remote_command(command)
        except Exception as e:
            logger.warning(f"Failed to create base directory: {e}")
    
    def _create_task_filesystem(self, task_hash: str, files: Optional[Dict[str, str]] = None) -> str:
        """创建任务专用文件系统"""
        task_dir = f"{self.config.base_sandbox_dir}/{task_hash}"
        
        # 创建目录
        commands = [
            f"mkdir -p {task_dir}",
            f"chmod 755 {task_dir}",
            f"cd {task_dir}"
        ]

        # 如果提供了文件，创建文件
        if files:
            for filename, content in files.items():
                # 安全的文件名检查
                if not is_safe_filename(filename):
                    raise ValueError(f"Unsafe filename: {filename}")
                
                try:
                    # 使用base64编码来避免特殊字符问题
                    encoded_content = base64.b64encode(content.encode('utf-8')).decode('ascii')
                    commands.append(f"echo '{encoded_content}' | base64 -d > '{filename}'")
                except Exception as e:
                    logger.error(f"Failed to encode file {filename}: {e}")
                    raise ValueError(f"Failed to process file {filename}: {e}")
        
        # 执行命令
        full_command = " && ".join(commands)
        result = self._execute_remote_command(full_command)
        
        # 检查目录创建是否成功
        if result['return_code'] != 0:
            raise RuntimeError(f"Failed to create task filesystem: {result['stderr']}")
        
        return task_dir
    
    def _execute_remote_command(self, command: str, working_dir: Optional[str] = None) -> Dict[str, Any]:
        """在EC2实例上执行命令"""
        try:
            # 如果指定了工作目录，添加cd命令
            if working_dir:
                command = f"cd {working_dir} && {command}"
            
            response = self.ssm_client.send_command(
                InstanceIds=[self.config.instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={
                    'commands': [command]  # 确保是列表格式
                },
                TimeoutSeconds=min(self.config.max_execution_time, 3600)  # 限制最大超时时间
            )
            
            command_id = response['Command']['CommandId']
            
            # 等待命令执行完成，增加超时处理
            waiter = self.ssm_client.get_waiter('command_executed')
            max_attempts = max(30, self.config.max_execution_time // 2)  # 动态调整等待次数
            waiter.wait(
                CommandId=command_id,
                InstanceId=self.config.instance_id,
                WaiterConfig={
                    'Delay': 2,
                    'MaxAttempts': max_attempts
                }
            )
            
            # 获取执行结果
            result = self.ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=self.config.instance_id
            )
            
            return {
                'stdout': result.get('StandardOutputContent', ''),
                'stderr': result.get('StandardErrorContent', ''),
                'status': result.get('Status', 'Unknown'),
                'return_code': result.get('ResponseCode', -1)
            }
            
        except Exception as e:
            logger.error(f"Remote command execution failed: {e}")
            return {
                'stdout': '',
                'stderr': str(e),
                'status': 'Failed',
                'return_code': 1
            }
    
    def check_instance_status(self) -> Dict[str, Any]:
        """检查EC2实例状态及负载"""
        try:
            # 获取实例基本信息
            response = self.ec2_client.describe_instances(
                InstanceIds=[self.config.instance_id]
            )
            
            if not response['Reservations']:
                return {'error': 'Instance not found'}
            
            instance = response['Reservations'][0]['Instances'][0]
            
            # 基本实例信息
            status_info = {
                'instance_id': instance['InstanceId'],
                'state': instance['State']['Name'],
                'instance_type': instance['InstanceType'],
                'public_ip': instance.get('PublicIpAddress'),
                'private_ip': instance.get('PrivateIpAddress'),
                'launch_time': instance['LaunchTime'].isoformat()
            }
            
            # 获取操作系统信息
            try:
                os_name = self._get_instance_os_name(instance)
                status_info['os_name'] = os_name
            except Exception as e:
                logger.warning(f"获取操作系统信息失败: {e}")
                status_info['os_name'] = 'Unknown'
            
            # 获取CPU使用率（如果实例正在运行）
            if instance['State']['Name'] == 'running':
                try:
                    cpu_utilization = self._get_cpu_utilization()
                    status_info['cpu_utilization'] = cpu_utilization
                except Exception as e:
                    logger.warning(f"获取CPU使用率失败: {e}")
                    status_info['cpu_utilization'] = {'error': str(e)}
            else:
                status_info['cpu_utilization'] = {'message': 'Instance not running'}
            
            return status_info
                
        except Exception as e:
            return {'error': str(e)}
    
    def _get_cpu_utilization(self) -> Dict[str, Any]:
        """获取EC2实例的CPU使用率"""
        try:
            import boto3
            from datetime import datetime, timedelta
            
            # 创建CloudWatch客户端
            cloudwatch = boto3.client('cloudwatch', region_name=self.config.region)
            
            # 设置时间范围（最近5分钟）
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(minutes=5)
            
            # 获取CPU使用率指标
            response = cloudwatch.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[
                    {
                        'Name': 'InstanceId',
                        'Value': self.config.instance_id
                    }
                ],
                StartTime=start_time,
                EndTime=end_time,
                Period=300,  # 5分钟间隔
                Statistics=['Average', 'Maximum']
            )
            
            if response['Datapoints']:
                # 获取最新的数据点
                latest_datapoint = max(response['Datapoints'], key=lambda x: x['Timestamp'])
                
                return {
                    'average': round(latest_datapoint['Average'], 2),
                    'maximum': round(latest_datapoint['Maximum'], 2),
                    'timestamp': latest_datapoint['Timestamp'].isoformat(),
                    'period_minutes': 5
                }
            else:
                return {
                    'message': 'No CPU data available (instance may be recently started)',
                    'period_minutes': 5
                }
                
        except Exception as e:
            raise Exception(f"CloudWatch API error: {str(e)}")
    
    def _get_instance_os_name(self, instance: Dict[str, Any]) -> str:
        """获取实例的操作系统名称"""
        try:
            ami_id = instance.get('ImageId')
            if not ami_id:
                return "Unknown"
            
            ami_response = self.ec2_client.describe_images(ImageIds=[ami_id])
            if not ami_response['Images']:
                return "Unknown"
            
            ami = ami_response['Images'][0]
            description = ami.get('Description', '')
            architecture = ami.get('Architecture', '')
            
            # 解析Ubuntu版本
            if 'Ubuntu' in description:
                if '24.04' in description:
                    os_name = "Ubuntu 24.04 LTS"
                elif '22.04' in description:
                    os_name = "Ubuntu 22.04 LTS"
                elif '20.04' in description:
                    os_name = "Ubuntu 20.04 LTS"
                else:
                    os_name = "Ubuntu Linux"

                if architecture.lower() == 'arm64':
                    os_name += " ARM64"
                
                return os_name
            
            return "Unknown"
            
        except Exception as e:
            logger.warning(f"获取操作系统名称失败: {e}")
            return "Unknown"
    
    def cleanup_old_tasks(self, hours: Optional[int] = None):
        """清理过期的任务目录"""
        cleanup_hours = hours or self.config.cleanup_after_hours
        
        try:
            # 查找并删除过期目录
            # 使用-mmin而不是-mtime来更精确地控制时间
            cleanup_minutes = cleanup_hours * 60
            command = f"""
            find {self.config.base_sandbox_dir} -maxdepth 1 -type d -mmin +{cleanup_minutes} ! -path {self.config.base_sandbox_dir} -exec rm -rf {{}} + 2>/dev/null || true
            """
            
            result = self._execute_remote_command(command)
            logger.info(f"Cleanup completed for tasks older than {cleanup_hours} hours")
            
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def _start_cleanup_timer(self):
        """启动清理定时器"""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
        
        # 创建定时器，每小时执行一次清理
        self._cleanup_timer = threading.Timer(
            self._cleanup_interval_hours * 3600,  # 转换为秒
            self._periodic_cleanup
        )
        self._cleanup_timer.daemon = True  # 守护线程，主程序退出时自动结束
        self._cleanup_timer.start()
        
        logger.info(f"自动清理定时器已启动")
    
    def _periodic_cleanup(self):
        """周期性清理任务"""
        try:
            logger.info("开始执行定期清理...")
            self.cleanup_old_tasks()  # 使用配置中的 cleanup_after_hours
            logger.info("定期清理完成")
        except Exception as e:
            logger.error(f"定期清理失败: {e}")
        finally:
            # 重新启动定时器，实现周期性执行
            self._start_cleanup_timer()
    
    def stop_cleanup_timer(self):
        """停止清理定时器"""
        if self._cleanup_timer:
            self._cleanup_timer.cancel()
            self._cleanup_timer = None
            logger.info("自动清理定时器已停止")
    
    def __del__(self):
        """析构函数，确保定时器被清理"""
        try:
            self.stop_cleanup_timer()
        except:
            pass  # 忽略析构时的异常
    
    def _get_task_files_by_hash(self, task_hash: str, filename: Optional[str] = None) -> Dict[str, str]:
        """根据task_hash获取任务目录中的文件内容"""
        task_dir = f"{self.config.base_sandbox_dir}/{task_hash}"
        files_content = {}
        
        try:
            if filename:
                # 获取特定文件
                command = f"cat {task_dir}/{filename}"
                result = self._execute_remote_command(command)
                if result['return_code'] == 0:
                    files_content[filename] = result['stdout']
            else:
                # 获取所有文件
                list_command = f"find {task_dir} -type f -exec basename {{}} \\;"
                list_result = self._execute_remote_command(list_command)
                
                if list_result['return_code'] == 0:
                    filenames = list_result['stdout'].strip().split('\n')
                    for fname in filenames:
                        if fname:
                            cat_command = f"cat {task_dir}/{fname}"
                            cat_result = self._execute_remote_command(cat_command)
                            if cat_result['return_code'] == 0:
                                files_content[fname] = cat_result['stdout']
            
        except Exception as e:
            logger.error(f"Failed to get task files: {e}")
        
        return files_content
