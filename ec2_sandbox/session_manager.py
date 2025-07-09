#!/usr/bin/env python3
"""
会话管理器
管理会话状态和文件路径, 会话ID由Gradio提供
"""

import time
import os
import threading
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)

class SessionData:
    """简化的会话数据"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = time.time()
        self.last_activity = time.time()
        self.task_count = 0
        self.lock = threading.Lock()
        
    def update_activity(self):
        """更新最后活动时间"""
        with self.lock:
            self.last_activity = time.time()
            self.task_count += 1
    
    def get_session_path(self, base_sandbox_dir: str) -> str:
        """获取会话的基础路径"""
        return f"{base_sandbox_dir}/{self.session_id}"

class SessionManager:
    """会话管理器 - 基于Gradio Session"""
    
    def __init__(self):
        self.sessions: Dict[str, SessionData] = {}
        self.lock = threading.Lock()
    
    def get_or_create_session(self, session_id: str) -> SessionData:
        """获取或创建用户会话"""
        if not session_id:
            raise ValueError("session_id is required")
            
        if session_id in self.sessions:
            session_data = self.sessions[session_id]
            session_data.update_activity()
            return session_data
        else:
            # 使用提供的session_id创建新会话
            with self.lock:
                if session_id not in self.sessions:
                    self.sessions[session_id] = SessionData(session_id)
                    logger.info(f"创建新会话: {session_id}")
                return self.sessions[session_id]
    
    def get_session(self, session_id: str) -> Optional[SessionData]:
        """获取会话数据"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def clear_session(self, session_id: str) -> bool:
        """清空会话（重置任务计数）"""
        session_data = self.get_session(session_id)
        if session_data:
            with session_data.lock:
                session_data.task_count = 0
                session_data.update_activity()
                logger.info(f"清空会话: {session_id}")
                return True
        return False
    
    def get_session_stats(self) -> Dict:
        """获取会话统计信息"""
        with self.lock:
            stats = {
                "total_sessions": len(self.sessions),
                "sessions": []
            }
            
            for session_id, session_data in self.sessions.items():
                stats["sessions"].append({
                    "session_id": session_id,
                    "task_count": session_data.task_count,
                    "created_at": session_data.created_at,
                    "last_activity": session_data.last_activity,
                    "age_minutes": (time.time() - session_data.created_at) / 60
                })
            
            return stats

# 全局会话管理器实例
global_session_manager = SessionManager()

class SessionContext:
    """会话上下文"""
    
    def __init__(self, session_data: SessionData, base_sandbox_dir: str):
        self.session_id = session_data.session_id
        self.session_data = session_data
        self.base_sandbox_dir = base_sandbox_dir
        
    @property
    def session_path(self) -> str:
        """当前会话的基础路径"""
        return f"{self.base_sandbox_dir}/{self.session_id}"
    
    def list_session_tasks(self) -> list:
        """列出当前会话的所有任务目录"""
        try:
            session_path = self.session_path
            if os.path.exists(session_path):
                tasks = []
                for item in os.listdir(session_path):
                    item_path = os.path.join(session_path, item)
                    if os.path.isdir(item_path):
                        # 获取目录的修改时间用于排序
                        mtime = os.path.getmtime(item_path)
                        tasks.append((item, mtime))
                # 按修改时间排序，最新的在前面
                tasks.sort(key=lambda x: x[1], reverse=True)
                return [task[0] for task in tasks]
            return []
        except Exception as e:
            logger.error(f"列出会话任务失败: {e}")
            return []

def create_session_context(session_id: str, base_sandbox_dir: str) -> SessionContext:
    """创建会话上下文"""
    if not session_id:
        raise ValueError("session_id is required")
    session_data = global_session_manager.get_or_create_session(session_id)
    return SessionContext(session_data, base_sandbox_dir)

def get_session_manager() -> SessionManager:
    """获取全局简化会话管理器"""
    return global_session_manager
