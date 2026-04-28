import sqlite3
import os
import threading
from typing import Optional, List, Dict
from config import config

class StateCache:
    """智能家居状态缓存工具类，使用 SQLite 存储各个设备节点的最新状态"""
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程安全的数据库连接"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self):
        """初始化数据库表结构"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS device_state (
                    sn TEXT,
                    did INTEGER,
                    node TEXT,
                    idx INTEGER,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (sn, did, node, idx)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_cache (
                    sn TEXT PRIMARY KEY,
                    project_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS local_scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    description TEXT,
                    actions_json TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
        finally:
            conn.close()

    def update_state(self, sn: str, did: int, node: str, idx: int, value: str):
        """更新设备状态副本"""
        with self._lock:
            conn = self._get_conn()
            try:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO device_state (sn, did, node, idx, value, updated_at)
                    VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(sn, did, node, idx) DO UPDATE SET
                        value = excluded.value,
                        updated_at = CURRENT_TIMESTAMP
                ''', (sn, did, node, idx, str(value)))
                conn.commit()
            finally:
                conn.close()

    def get_state(self, sn: str, did: int, node: str, idx: int = 0) -> str:
        """获取指定节点的状态值"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT value FROM device_state
                WHERE sn = ? AND did = ? AND node = ? AND idx = ?
            ''', (sn, did, node, idx))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    def get_all_states(self, sn: str, did: int) -> Dict[str, str]:
        """获取该设备的所有状态"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT node, idx, value, updated_at FROM device_state
                WHERE sn = ? AND did = ?
            ''', (sn, did))
            states = {}
            for row in cursor.fetchall():
                node, idx, value, updated_at = row
                states[f"{node}:{idx}"] = value
            return states
        finally:
            conn.close()

    def save_project(self, sn: str, project_json: str):
        """保存或更新网关工程数据的 JSON 缓存"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO project_cache (sn, project_json, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(sn) DO UPDATE SET
                    project_json = excluded.project_json,
                    updated_at = CURRENT_TIMESTAMP
            ''', (sn, project_json))
            conn.commit()
        finally:
            conn.close()

    def get_cached_project(self, sn: str) -> Optional[str]:
        """获取本地缓存的工程数据 JSON 字符串"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT project_json FROM project_cache WHERE sn = ?', (sn,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            conn.close()

    def get_all_cached_sns(self) -> List[str]:
        """获取本地数据库中所有已缓存过工程的网关 SN 列表"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT sn FROM project_cache')
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def save_local_scene(self, name: str, actions_json: str, description: str = ""):
        """保存或更新本地场景"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO local_scenes (name, actions_json, description, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    actions_json = excluded.actions_json,
                    description = excluded.description,
                    updated_at = CURRENT_TIMESTAMP
            ''', (name, actions_json, description))
            conn.commit()
        finally:
            conn.close()

    def get_local_scene(self, name: str) -> Optional[dict]:
        """根据名称获取本地场景"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT name, actions_json, description FROM local_scenes WHERE name = ?', (name,))
            row = cursor.fetchone()
            if row:
                return {"name": row[0], "actions_json": row[1], "description": row[2]}
            return None
        finally:
            conn.close()

    def list_all_local_scenes(self) -> List[dict]:
        """列出所有本地场景"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT name, description FROM local_scenes')
            return [{"name": row[0], "description": row[1]} for row in cursor.fetchall()]
        finally:
            conn.close()

    def delete_local_scene(self, name: str) -> bool:
        """删除本地场景"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM local_scenes WHERE name = ?', (name,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

state_cache = StateCache(config.DB_PATH)
