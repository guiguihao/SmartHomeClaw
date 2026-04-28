import sqlite3
import os
import json
import threading
from datetime import datetime
from typing import Optional
import sys

class AuditLogger:
    """智能家居 MQTT 审计日志记录器，支持按月自动分月存储数据库"""
    
    def __init__(self, log_dir: str = "."):
        self.log_dir = log_dir
        self._current_db_path: Optional[str] = None
        self._last_checked_month: Optional[str] = None
        self._lock = threading.Lock()

    def _get_db_path(self) -> str:
        """获取当前月份对应的数据库路径，例如: smarthome_logs_2026_04.db"""
        now = datetime.now()
        month_suffix = now.strftime("%Y_%m")
        
        if self._last_checked_month == month_suffix and self._current_db_path:
            return self._current_db_path
        
        db_name = f"smarthome_logs_{month_suffix}.db"
        db_path = os.path.join(self.log_dir, db_name)
        
        self._last_checked_month = month_suffix
        self._current_db_path = db_path
        
        self._init_db(db_path)
        return db_path

    def _init_db(self, db_path: str):
        """初始化审计日志表结构"""
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    direction TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    sn TEXT,
                    did INTEGER,
                    node TEXT,
                    idx INTEGER DEFAULT 0,
                    value TEXT,
                    msgid TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_msgid ON audit_log (msgid)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sn_did ON audit_log (sn, did)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON audit_log (timestamp)")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error initializing audit database {db_path}: {e}", file=sys.stderr)

    def log_message(self, direction: str, topic: str, payload: str, msgid: str = None):
        """记录一条 MQTT 消息。如果包含列表结构(ctrllist/statlist)，则平铺化入库。"""
        db_path = self._get_db_path()
        
        sn_val = None
        items = []
        
        try:
            data_dict = json.loads(payload)
            sn_val = data_dict.get('sn')
            msgid = msgid or data_dict.get('msgid')
            
            data_section = data_dict.get('data', {})
            
            if 'statlist' in data_section:
                for item in data_section['statlist']:
                    did = item.get('did')
                    node = item.get('node')
                    if did is not None and node is not None:
                        items.append((
                            did,
                            node,
                            item.get('idx', 0),
                            str(item.get('value'))
                        ))
            
            elif 'devlist' in data_section:
                for dev in data_section['devlist']:
                    if not isinstance(dev, dict):
                        continue
                    parent_did = dev.get('did')
                    if parent_did is None:
                        continue
                    for stat in dev.get('statlist', []):
                        if not isinstance(stat, dict):
                            continue
                        node = stat.get('node')
                        if node is not None:
                            items.append((
                                parent_did,
                                node,
                                stat.get('idx', 0),
                                str(stat.get('value'))
                            ))
            
            elif 'ctrllist' in data_section:
                for item in data_section['ctrllist']:
                    did = item.get('did')
                    node = item.get('node')
                    if did is not None and node is not None:
                        items.append((
                            did,
                            node,
                            item.get('idx', 0),
                            str(item.get('value'))
                        ))
        except json.JSONDecodeError as e:
            print(f"AuditLogger: JSON parse error: {e}", file=sys.stderr)
        except Exception as e:
            print(f"AuditLogger: Unexpected error parsing payload: {e}", file=sys.stderr)

        try:
            with self._lock:
                conn = sqlite3.connect(db_path, timeout=10.0)
                try:
                    if not items:
                        conn.execute("""
                            INSERT INTO audit_log (direction, topic, sn, msgid)
                            VALUES (?, ?, ?, ?)
                        """, (direction, topic, sn_val, msgid))
                    else:
                        for did, node, idx, val in items:
                            conn.execute("""
                                INSERT INTO audit_log (direction, topic, sn, did, node, idx, value, msgid)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (direction, topic, sn_val, did, node, idx, val, msgid))
                    conn.commit()
                finally:
                    conn.close()
        except Exception as e:
            print(f"Failed to write audit log: {e}", file=sys.stderr)

audit_logger = AuditLogger()
