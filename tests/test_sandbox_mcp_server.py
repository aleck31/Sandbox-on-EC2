#!/usr/bin/env python3
"""
EC2 Sandbox MCP Client Test Script

Simple test client for the EC2 Sandbox MCP Server
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    print("Error: MCP library not found. Please install with: uv add mcp")
    sys.exit(1)

class EC2SandboxMCPClient:
    """Simple MCP client for testing EC2 Sandbox server"""
    
    def __init__(self):
        self.session = None
    
    async def connect_and_test(self):
        """Connect to server and run tests"""
        # Get config file path relative to project root
        config_path = Path(__file__).parent.parent / "config.json"
        
        server_params = StdioServerParameters(
            command="uv",
            args=["run", "python", "-m", "ec2_sandbox_mcp.server"],
            env={"EC2_SANDBOX_CONFIG": str(config_path)},
            cwd=str(Path(__file__).parent.parent)  # Set working directory to project root
        )
        
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Initialize the connection
                await session.initialize()
                logger.info("Connected to EC2 Sandbox MCP Server")
                
                # Run all tests
                await self.test_list_tools(session)
                await self.test_list_resources(session)
                await self.test_list_environments(session)
                await self.test_check_status(session)
                await self.test_execute_code(session)
                await self.test_execute_with_files(session)
                await self.test_get_task_files(session)
    
    async def test_list_tools(self, session):
        """List available tools"""
        print("\n=== Available Tools ===")
        tools = await session.list_tools()
        for tool in tools.tools:
            print(f"- {tool.name}: {tool.description}")
        return tools.tools
    
    async def test_list_resources(self, session):
        """List available resources"""
        print("\n=== Available Resources ===")
        resources = await session.list_resources()
        for resource in resources.resources:
            print(f"- {resource.uri}: {resource.name}")
        return resources.resources
    
    async def test_list_environments(self, session):
        """Test list environments tool"""
        print("\n=== Testing: List Environments ===")
        result = await session.call_tool("list_environments", {})
        print(result.content[0].text)
    
    async def test_check_status(self, session):
        """Test check sandbox status"""
        print("\n=== Testing: Check Sandbox Status ===")
        result = await session.call_tool("check_sandbox_status", {})
        print(result.content[0].text)
    
    async def test_execute_code(self, session):
        """Test code execution"""
        print("\n=== Testing: Execute Python Code ===")
        
        code = """
import sys
import os
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print("Hello from EC2 Sandbox MCP!")

# Simple calculation
result = sum(range(1, 11))
print(f"Sum of 1-10: {result}")
"""
        
        result = await session.call_tool("execute_code_in_sandbox", {
            "code": code,
            "runtime": "python",
            "task_id": "mcp-test-001"
        })
        print(result.content[0].text)
    
    async def test_execute_with_files(self, session):
        """Test code execution with files"""
        print("\n=== Testing: Execute Code with Files ===")
        
        code = """
import json
import csv

# Read the config file
with open('test_config.json', 'r') as f:
    config = json.load(f)
print(f"Config loaded: {config}")

# Read CSV data
with open('test_data.csv', 'r') as f:
    reader = csv.DictReader(f)
    data = list(reader)

print(f"CSV data ({len(data)} rows):")
for row in data:
    print(f"  {row}")

# Create output file
output = {
    "processed_at": "2024-07-24",
    "total_rows": len(data),
    "config": config
}

with open('output.json', 'w') as f:
    json.dump(output, f, indent=2)

print("Output file created: output.json")
"""
        
        files = {
            "test_config.json": json.dumps({"environment": "test", "debug": True}),
            "test_data.csv": "name,age,city\nAlice,25,New York\nBob,30,San Francisco\nCharlie,35,Chicago"
        }
        
        result = await session.call_tool("execute_code_in_sandbox", {
            "code": code,
            "runtime": "python",
            "task_id": "mcp-test-002",
            "files": files
        })
        print(result.content[0].text)
    
    async def test_get_task_files(self, session):
        """Test getting task files"""
        print("\n=== Testing: Get Task Files ===")
        
        # First, execute code that creates files
        code = """
import json
import datetime

# Create multiple output files
data = {
    "timestamp": datetime.datetime.now().isoformat(),
    "message": "Hello from MCP test",
    "numbers": list(range(1, 6))
}

with open('result.json', 'w') as f:
    json.dump(data, f, indent=2)

with open('log.txt', 'w') as f:
    f.write("MCP Test Log\\n")
    f.write("=============\\n")
    f.write(f"Executed at: {data['timestamp']}\\n")
    f.write("Test completed successfully\\n")

print("Files created: result.json, log.txt")
"""
        
        # Execute code
        result = await session.call_tool("execute_code_in_sandbox", {
            "code": code,
            "runtime": "python",
            "task_id": "mcp-test-003"
        })
        
        # Extract task hash from result
        result_text = result.content[0].text
        task_hash = None
        for line in result_text.split('\n'):
            if 'Task Hash:' in line:
                task_hash = line.split('Task Hash:')[1].strip()
                break
        
        if task_hash:
            print(f"Getting files for task hash: {task_hash}")
            files_result = await session.call_tool("get_task_files", {
                "task_hash": task_hash
            })
            print(files_result.content[0].text)
        else:
            print("Could not extract task hash from execution result")

async def main():
    """Main test function"""
    print("EC2 Sandbox MCP Client Test")
    print("=" * 40)
    
    # Check if config file exists (look in parent directory)
    config_path = Path(__file__).parent.parent / "config.json"
    if not config_path.exists():
        print("Error: config.json not found. Please create it from config.json.template")
        return
    
    client = EC2SandboxMCPClient()
    try:
        await client.connect_and_test()
        print("\n=== All Tests Completed Successfully ===")
    except Exception as e:
        logger.error(f"Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
