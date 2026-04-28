import sqlite3
import os
import glob
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from config import config

class HistoryAnalyzer:
    """从按月分库的 audit_log 中读取历史数据并统计分析"""
    
    def __init__(self, log_dir: str = "."):
        self.log_dir = log_dir
    
    def _get_monthly_dbs(self) -> List[str]:
        """获取所有按月分库的审计日志数据库文件"""
        pattern = os.path.join(self.log_dir, "smarthome_logs_*.db")
        return sorted(glob.glob(pattern))
    
    def _get_db_for_period(self, start_date: datetime, end_date: datetime) -> List[str]:
        """获取指定时间范围覆盖的月度数据库"""
        dbs = []
        current = start_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = end_date.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        while current <= end:
            month_suffix = current.strftime("%Y_%m")
            db_path = os.path.join(self.log_dir, f"smarthome_logs_{month_suffix}.db")
            if os.path.exists(db_path):
                dbs.append(db_path)
            current = (current + timedelta(days=32)).replace(day=1)
        
        return dbs
    
    def _query_dbs(self, dbs: List[str], sql: str, params: tuple) -> List[tuple]:
        """跨库查询，合并结果"""
        results = []
        for db_path in dbs:
            try:
                conn = sqlite3.connect(db_path, timeout=10.0)
                cursor = conn.cursor()
                cursor.execute(sql, params)
                results.extend(cursor.fetchall())
                conn.close()
            except Exception:
                continue
        return results
    
    def get_history(self, sn: str, did: int, nodes: List[str],
                    hours: int = 24, limit_per_node: int = 500) -> Dict[str, List[Dict]]:
        """获取指定节点的历史时序数据"""
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        dbs = self._get_db_for_period(start_time, end_time)
        
        if not dbs:
            return {node: [] for node in nodes}
        
        result = {}
        for node in nodes:
            rows = self._query_dbs(dbs, '''
                SELECT value, timestamp FROM audit_log
                WHERE sn = ? AND did = ? AND node = ?
                AND timestamp >= ?
                ORDER BY timestamp ASC
                LIMIT ?
            ''', (sn, did, node, start_time.strftime('%Y-%m-%d %H:%M:%S'), limit_per_node))
            
            result[node] = [{"value": row[0], "time": row[1]} for row in rows]
        
        return result
    
    def get_today_summary(self, sn: str, did: int, nodes: List[str]) -> Dict:
        """获取今天的数据摘要（min/max/avg/count）"""
        today = datetime.now().strftime('%Y-%m-%d')
        db_path = os.path.join(self.log_dir, f"smarthome_logs_{datetime.now().strftime('%Y_%m')}.db")
        
        if not os.path.exists(db_path):
            return {node: None for node in nodes}
        
        summary = {}
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            cursor = conn.cursor()
            for node in nodes:
                cursor.execute('''
                    SELECT
                        MIN(CAST(value AS REAL)) as min_val,
                        MAX(CAST(value AS REAL)) as max_val,
                        AVG(CAST(value AS REAL)) as avg_val,
                        COUNT(*) as count,
                        value as latest_val
                    FROM audit_log
                    WHERE sn = ? AND did = ? AND node = ?
                    AND DATE(timestamp, 'localtime') = ?
                ''', (sn, did, node, today))
                row = cursor.fetchone()
                if row and row[3] > 0:
                    summary[node] = {
                        "min": round(row[0], 1) if row[0] is not None else None,
                        "max": round(row[1], 1) if row[1] is not None else None,
                        "avg": round(row[2], 1) if row[2] is not None else None,
                        "count": row[3],
                        "latest": row[4]
                    }
                else:
                    summary[node] = None
            conn.close()
        except Exception:
            summary = {node: None for node in nodes}
        
        return summary
    
    def get_period_summary(self, sn: str, did: int, nodes: List[str],
                           days: int = 7) -> Dict:
        """获取多天数据摘要（按天分组）"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)
        dbs = self._get_db_for_period(start_time, end_time)
        
        if not dbs:
            return {node: [] for node in nodes}
        
        summary = {}
        for node in nodes:
            rows = self._query_dbs(dbs, '''
                SELECT
                    DATE(timestamp, 'localtime') as day,
                    MIN(CAST(value AS REAL)) as min_val,
                    MAX(CAST(value AS REAL)) as max_val,
                    AVG(CAST(value AS REAL)) as avg_val,
                    COUNT(*) as count
                FROM audit_log
                WHERE sn = ? AND did = ? AND node = ?
                AND DATE(timestamp, 'localtime') >= DATE('now', 'localtime', ?)
                GROUP BY DATE(timestamp, 'localtime')
                ORDER BY day ASC
            ''', (sn, did, node, f'-{days} days'))
            
            summary[node] = [{
                "date": row[0],
                "min": round(row[1], 1) if row[1] is not None else None,
                "max": round(row[2], 1) if row[2] is not None else None,
                "avg": round(row[3], 1) if row[3] is not None else None,
                "count": row[4]
            } for row in rows]
        
        return summary
    
    def get_available_months(self) -> List[str]:
        """获取有历史数据的月份列表"""
        dbs = self._get_monthly_dbs()
        months = []
        for db in dbs:
            match = re.search(r'smarthome_logs_(\d{4}_\d{2})\.db', db)
            if match:
                months.append(match.group(1))
        return sorted(months)

history_analyzer = HistoryAnalyzer(config._BASE_DIR)
