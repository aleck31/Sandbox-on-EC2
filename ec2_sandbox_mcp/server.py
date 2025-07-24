#!/usr/bin/env python3
"""
EC2 Sandbox MCP Server

A Model Context Protocol server that provides secure code execution capabilities
using EC2 instances as sandboxes.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent directory to path to import our modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from config_manager import ConfigManager
from ec2_sandbox.core import EC2SandboxEnv
from ec2_sandbox.utils import get_logger

# MCP imports
from mcp.server.fastmcp import FastMCP

# Setup logging
logger = get_logger(__name__)

class EC2SandboxMCPServer:
    """EC2 Sandbox MCP Server implementation using FastMCP"""
    
    def __init__(self):
        self.mcp = FastMCP("EC2 Sandbox")
        self.config_manager: Optional[ConfigManager] = None
        self.sandbox_envs: Dict[str, EC2SandboxEnv] = {}
        self.current_environment = "default"
        
        # Register tools
        self._register_tools()
        self._register_resources()
    
    def _register_tools(self):
        """Register MCP tools"""
        
        @self.mcp.tool()
        def execute_code_in_sandbox(
            code: str,
            runtime: str = "python",
            task_id: Optional[str] = None,
            files: Optional[Dict[str, str]] = None,
            env_vars: Optional[Dict[str, str]] = None,
            create_filesystem: bool = True,
            environment: str = "sandbox-default"
        ) -> str:
            """Execute code in EC2 sandbox environment
            
            Args:
                code: Code to execute
                runtime: Runtime environment (python, node, bash, etc.)
                task_id: Optional task identifier
                files: Files to create {filename: content}
                env_vars: Environment variables {key: value}
                create_filesystem: Create isolated filesystem
                environment: Sandbox environment name
            
            Returns:
                Execution result with output and metadata
            """
            try:
                # Get sandbox environment
                sandbox_env = self._get_sandbox_env(environment)
                sandbox = sandbox_env.create_sandbox_instance(task_id or "mcp-task")
                
                # Execute code
                result = sandbox.execute_code(
                    code=code,
                    runtime=runtime,
                    files=files or {},
                    env_vars=env_vars or {},
                    create_filesystem=create_filesystem
                )
                
                # Format response
                response_text = f"**Execution Result:**\n"
                response_text += f"- Success: {result.success}\n"
                response_text += f"- Return Code: {result.return_code}\n"
                response_text += f"- Task Hash: {result.task_hash}\n"
                response_text += f"- Execution Time: {result.execution_time:.2f}s\n"
                
                if result.stdout:
                    response_text += f"\n**Output:**\n```\n{result.stdout}\n```\n"
                
                if result.stderr:
                    response_text += f"\n**Errors:**\n```\n{result.stderr}\n```\n"
                
                if result.files_created:
                    response_text += f"\n**Files Created:**\n"
                    for filename in result.files_created:
                        response_text += f"- {filename}\n"
                
                return response_text
                
            except Exception as e:
                logger.error(f"Code execution failed: {str(e)}")
                return f"Error: {str(e)}"
        
        @self.mcp.tool()
        def get_task_files(
            task_hash: str,
            filename: Optional[str] = None,
            environment: str = "sandbox-default"
        ) -> str:
            """Get files from a completed task
            
            Args:
                task_hash: Task hash identifier
                filename: Specific filename to retrieve (optional)
                environment: Sandbox environment name
            
            Returns:
                Task files content
            """
            try:
                # Get sandbox environment
                sandbox_env = self._get_sandbox_env(environment)
                sandbox = sandbox_env.create_sandbox_instance(task_hash)
                
                # Get files
                files = sandbox.get_task_files(filename)
                
                if not files:
                    return "No files found for the specified task."
                
                response_text = f"**Task Files (Hash: {task_hash}):**\n\n"
                
                for fname, content in files.items():
                    response_text += f"**{fname}:**\n```\n{content}\n```\n\n"
                
                return response_text
                
            except Exception as e:
                logger.error(f"Get task files failed: {str(e)}")
                return f"Error: {str(e)}"
        
        @self.mcp.tool()
        def cleanup_expired_tasks(
            hours: Optional[int] = None,
            environment: str = "sandbox-default"
        ) -> str:
            """Clean up expired task directories
            
            Args:
                hours: Clean tasks older than this many hours
                environment: Sandbox environment name
            
            Returns:
                Cleanup result
            """
            try:
                # Get sandbox environment
                sandbox_env = self._get_sandbox_env(environment)
                sandbox = sandbox_env.create_sandbox_instance("temp")
                
                # Cleanup
                result = sandbox.cleanup_expired_tasks(hours)
                
                return f"Cleanup completed. Removed {result.get('cleaned_count', 0)} expired task directories."
                
            except Exception as e:
                logger.error(f"Cleanup failed: {str(e)}")
                return f"Error: {str(e)}"
        
        @self.mcp.tool()
        def check_sandbox_status(environment: str = "sandbox-default") -> str:
            """Check sandbox environment status
            
            Args:
                environment: Sandbox environment name
            
            Returns:
                Sandbox status information
            """
            try:
                # Get sandbox environment
                sandbox_env = self._get_sandbox_env(environment)
                
                # Check status
                status = sandbox_env.check_instance_status()
                
                response_text = f"**Sandbox Status ({environment}):**\n"
                response_text += f"- Instance ID: {sandbox_env.config.instance_id}\n"
                response_text += f"- Region: {sandbox_env.config.region}\n"
                response_text += f"- Status: {status.get('state', 'Unknown')}\n"
                
                if 'runtime_info' in status:
                    response_text += f"- Available Runtimes: {', '.join(status['runtime_info'])}\n"
                
                return response_text
                
            except Exception as e:
                logger.error(f"Status check failed: {str(e)}")
                return f"Failed to check status: {str(e)}"
        
        @self.mcp.tool()
        def list_environments() -> str:
            """List available sandbox environments
            
            Returns:
                List of available environments
            """
            try:
                if not self.config_manager:
                    return "Configuration manager not initialized"
                
                environments = self.config_manager.list_environments()
                
                response_text = "**Available Sandbox Environments:**\n\n"
                for env_name in environments:
                    try:
                        config = self.config_manager.get_sandbox_config(env_name)
                        response_text += f"- **{env_name}**\n"
                        response_text += f"  - Instance: {getattr(config, 'instance_id', 'N/A')}\n"
                        response_text += f"  - Region: {getattr(config, 'region', 'N/A')}\n"
                        if env_name == self.current_environment:
                            response_text += f"  - Status: **CURRENT**\n"
                        response_text += "\n"
                    except Exception as e:
                        response_text += f"- **{env_name}**: Error loading config - {str(e)}\n\n"
                
                return response_text
                
            except Exception as e:
                logger.error(f"List environments failed: {str(e)}")
                return f"Error: {str(e)}"
        
        @self.mcp.tool()
        def switch_environment(environment: str) -> str:
            """Switch to a different sandbox environment
            
            Args:
                environment: Environment name to switch to
            
            Returns:
                Switch result
            """
            try:
                if not self.config_manager:
                    return "Configuration manager not initialized"
                
                # Validate environment exists
                environments = self.config_manager.list_environments()
                if environment not in environments:
                    return f"Environment '{environment}' not found. Available: {', '.join(environments)}"
                
                # Switch environment
                self.current_environment = environment
                
                return f"Switched to environment: {environment}"
                
            except Exception as e:
                logger.error(f"Switch environment failed: {str(e)}")
                return f"Error: {str(e)}"
    
    def _register_resources(self):
        """Register MCP resources"""
        
        @self.mcp.resource("sandbox://{environment}")
        def get_sandbox_config(environment: str) -> str:
            """Get sandbox environment configuration
            
            Args:
                environment: Environment name
            
            Returns:
                Environment configuration (sanitized)
            """
            try:
                if not self.config_manager:
                    return "Configuration manager not initialized"
                
                config = self.config_manager.get_sandbox_config(environment)
                # Remove sensitive information
                safe_config = {k: v for k, v in config.items() 
                             if k not in ['access_key_id', 'secret_access_key', 'session_token']}
                
                import json
                return json.dumps(safe_config, indent=2)
                
            except Exception as e:
                logger.error(f"Get config failed: {str(e)}")
                return f"Error: {str(e)}"
    
    def _get_sandbox_env(self, environment: str) -> EC2SandboxEnv:
        """Get or create sandbox environment"""
        if environment not in self.sandbox_envs:
            if not self.config_manager:
                raise ValueError("Configuration manager not initialized")
            
            config = self.config_manager.get_sandbox_config(environment)
            self.sandbox_envs[environment] = EC2SandboxEnv(config)
        
        return self.sandbox_envs[environment]
    
    def initialize(self):
        """Initialize the server"""
        import os
        
        # Load configuration
        config_path = os.environ.get('EC2_SANDBOX_CONFIG', 'config.json')
        
        if os.path.exists(config_path):
            self.config_manager = ConfigManager(config_path)
            logger.info(f"Loaded configuration from {config_path}")
            
            # Set default environment
            environments = self.config_manager.list_environments()
            if environments:
                if 'sandbox-default' in environments:
                    self.current_environment = 'sandbox-default'
                elif 'default' in environments:
                    self.current_environment = 'default'
                else:
                    self.current_environment = environments[0]
                logger.info(f"Default environment: {self.current_environment}")
        else:
            logger.warning(f"Configuration file not found: {config_path}")
    
    def run(self):
        """Run the MCP server"""
        self.initialize()
        self.mcp.run()

def main():
    """Main entry point"""
    server = EC2SandboxMCPServer()
    server.run()

if __name__ == "__main__":
    main()
