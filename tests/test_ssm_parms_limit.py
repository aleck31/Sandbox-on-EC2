#!/usr/bin/env python3
"""
最终测试：在70KB和75KB之间找到精确边界
"""

import os
import sys
import boto3
import base64
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config_manager import ConfigManager


def test_final_boundary():
    """在70KB和75KB之间找到精确边界"""
    
    config_manager = ConfigManager('config.json')
    config = config_manager.get_config('default')
    
    session = boto3.Session(profile_name=config.aws_profile)
    ssm_client = session.client('ssm', region_name=config.region)
    
    print(f"🔍 SSM参数长度边界测试: 70KB - 75KB")
    
    # 在70KB到75KB之间测试
    test_sizes = [
        70500,   # 68.8KB
        71000,   # 69.3KB
        71500,   # 69.8KB
        72000,   # 70.3KB
        72500,   # 70.8KB
        73000,   # 71.3KB
        73500,   # 71.8KB
        74000,   # 72.3KB
        74500,   # 72.8KB
    ]
    
    results = {}
    boundary_found = False
    last_success = 0
    first_failure = 0
    
    for size in test_sizes:
        print(f"\n🧪 测试 {size:,} 字节 ({size/1024:.1f}KB)")
        
        # 生成测试代码
        base_code = 'print("Boundary test")\nprint(f"Code size: {len(open(__file__).read())} bytes")\n'
        padding = '#' * (size - len(base_code.encode('utf-8')))
        test_code = base_code + padding
        actual_size = len(test_code.encode('utf-8'))
        
        try:
            encoded_code = base64.b64encode(test_code.encode('utf-8')).decode('ascii')
            command = f"echo '{encoded_code}' | base64 -d > test.py && python3 test.py"
            
            print(f"   代码: {actual_size:,} 字节, 命令: {len(command):,} 字节")
            
            response = ssm_client.send_command(
                InstanceIds=[config.instance_id],
                DocumentName="AWS-RunShellScript",
                Parameters={'commands': [command]},
                TimeoutSeconds=30
            )
            
            print(f"   ✅ 发送成功")
            results[actual_size] = 'SUCCESS'
            last_success = actual_size
            
        except Exception as e:
            print(f"   ❌ 发送失败: {e}")
            results[actual_size] = f"FAILED: {str(e)}"
            if first_failure == 0:
                first_failure = actual_size
                boundary_found = True
        
        time.sleep(1)
        
        # 如果找到边界就停止
        if boundary_found:
            break
    
    print(f"\n🎯 最终结果:")
    print(f"✅ 最大成功: {last_success:,} 字节 ({last_success/1024:.1f}KB)")
    if first_failure > 0:
        print(f"❌ 最小失败: {first_failure:,} 字节 ({first_failure/1024:.1f}KB)")
    
    # 建议限制
    safe_limit = last_success - 2048  # 减去2KB安全余量
    print(f"\n💡 推荐安全限制: {safe_limit:,} 字节 ({safe_limit/1024:.1f}KB)")
    
    return last_success, first_failure

if __name__ == "__main__":
    test_final_boundary()
