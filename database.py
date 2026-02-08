import sqlite3
import hashlib
import pandas as pd
from datetime import datetime

class DBManager:
    def __init__(self, db_path='investor_assistant.db'):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """初始化数据库表结构"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 用户表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    uid INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    status TEXT DEFAULT 'active',
                    can_backtest INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # 兼容性升级
            try:
                cursor.execute("ALTER TABLE users ADD COLUMN total_tokens INTEGER DEFAULT 0")
            except: pass
            
            # Token 消耗日志表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS token_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid INTEGER,
                    action_type TEXT,
                    stock_code TEXT,
                    prompt_tokens INTEGER,
                    completion_tokens INTEGER,
                    total_tokens INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uid) REFERENCES users (uid)
                )
            ''')

            # 自选股表 (包含标签)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid INTEGER,
                    stock_code TEXT NOT NULL,
                    tag TEXT DEFAULT '未分类',
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uid) REFERENCES users (uid),
                    UNIQUE(uid, stock_code)
                )
            ''')
            
            # 每日自动建议表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid INTEGER,
                    stock_code TEXT NOT NULL,
                    date TEXT NOT NULL,
                    tech_action TEXT,
                    tech_reason TEXT,
                    sent_action TEXT,
                    sent_reason TEXT,
                    price REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (uid) REFERENCES users (uid),
                    UNIQUE(uid, stock_code, date)
                )
            ''')
            conn.commit()

    # --- 用户管理 ---
    def register_user(self, username, email, password, role='user'):
        """注册新用户"""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        # admin 默认有权限
        can_backtest = 1 if role.lower() == 'admin' else 0
        try:
            with self._get_connection() as conn:
                conn.execute(
                    'INSERT INTO users (username, email, password_hash, role, status, can_backtest) VALUES (?, ?, ?, ?, ?, ?)', 
                    (username, email, pw_hash, role, 'active', can_backtest)
                )
                return True, "注册成功"
        except sqlite3.IntegrityError as e:
            err_msg = str(e)
            if 'username' in err_msg: return False, "用户名已存在"
            if 'email' in err_msg: return False, "该邮箱已被注册"
            return False, f"注册失败: {err_msg}"

    def login_user(self, username, password):
        """验证登录并在状态正常时返回用户信息"""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT uid, username, email, role, status, can_backtest FROM users WHERE username = ? AND password_hash = ?', 
                         (username, pw_hash))
            user = cursor.fetchone()
            if user:
                user_dict = dict(user)
                if user_dict['status'] != 'active':
                    return "disabled"
                # 转换 bool
                user_dict['can_backtest'] = bool(user_dict['can_backtest'])
                return user_dict
            return None

    def get_all_users(self):
        """管理员特权：获取所有用户信息（包含Token统计）"""
        with self._get_connection() as conn:
            return pd.read_sql_query('SELECT uid, username, email, role, status, can_backtest, total_tokens, created_at FROM users', conn)

    def update_user_status(self, uid, new_status):
        """管理员特权：禁用/启用用户"""
        with self._get_connection() as conn:
            conn.execute('UPDATE users SET status = ? WHERE uid = ?', (new_status, uid))
            conn.commit()

    def update_user_backtest_permission(self, uid, can_backtest):
        """管理员特权：授权/取消回测权限"""
        with self._get_connection() as conn:
            conn.execute('UPDATE users SET can_backtest = ? WHERE uid = ?', (1 if can_backtest else 0, uid))
            conn.commit()

    # --- 自选股与标签管理 ---
    def add_to_watchlist(self, uid, stock_code, tag='未分类'):
        """添加股票到自选，带标签"""
        try:
            with self._get_connection() as conn:
                conn.execute('INSERT OR REPLACE INTO watchlist (uid, stock_code, tag) VALUES (?, ?, ?)', 
                           (uid, stock_code, tag))
                return True
        except Exception as e:
            print(f"添加失败: {e}")
            return False

    def remove_from_watchlist(self, uid, stock_code):
        """从自选移除"""
        with self._get_connection() as conn:
            conn.execute('DELETE FROM watchlist WHERE uid = ? AND stock_code = ?', (uid, stock_code))

    def get_user_watchlist(self, uid):
        """获取用户的所有自选股"""
        with self._get_connection() as conn:
            query = "SELECT stock_code, tag FROM watchlist WHERE uid = ?"
            return pd.read_sql_query(query, conn, params=(uid,))

    def get_tags(self, uid):
        """获取用户已创建的所有唯一标签"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT DISTINCT tag FROM watchlist WHERE uid = ?', (uid,))
            return [row[0] for row in cursor.fetchall()]

    def update_stock_tag(self, uid, stock_code, new_tag):
        """更新已有股票的标签"""
        with self._get_connection() as conn:
            conn.execute('UPDATE watchlist SET tag = ? WHERE uid = ? AND stock_code = ?', 
                       (new_tag, uid, stock_code))

    # --- 每日建议存储 ---
    def save_daily_recommendation(self, uid, stock_code, date, tech_res, sent_res, price):
        """保存每日自动生成的建议"""
        try:
            with self._get_connection() as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO daily_recommendations 
                    (uid, stock_code, date, tech_action, tech_reason, sent_action, sent_reason, price)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (uid, stock_code, date, tech_res['action'], tech_res['reason'], 
                      sent_res['action'], sent_res['reason'], price))
                return True
        except Exception as e:
            print(f"保存每日建议失败: {e}")
            return False

    def get_daily_recommendations(self, uid, date=None):
        """获取历史建议，如果提供日期则查询特定日期"""
        with self._get_connection() as conn:
            if date:
                query = "SELECT * FROM daily_recommendations WHERE uid = ? AND date = ? ORDER BY created_at DESC"
                return pd.read_sql_query(query, conn, params=(uid, date))
            else:
                query = "SELECT DISTINCT date FROM daily_recommendations WHERE uid = ? ORDER BY date DESC"
                return pd.read_sql_query(query, conn, params=(uid,))

    def get_recommendations_by_date(self, uid, date):
        """获取特定日期的所有建议"""
        with self._get_connection() as conn:
            query = "SELECT * FROM daily_recommendations WHERE uid = ? AND date = ?"
            return pd.read_sql_query(query, conn, params=(uid, date))
    def log_token_usage(self, uid, action_type, stock_code, prompt, completion):
        """记录并累加用户的 token 消耗"""
        total = prompt + completion
        try:
            with self._get_connection() as conn:
                # 1. 记录明细
                conn.execute('''
                    INSERT INTO token_logs (uid, action_type, stock_code, prompt_tokens, completion_tokens, total_tokens)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (uid, action_type, stock_code, prompt, completion, total))
                # 2. 累加到用户主表
                conn.execute('UPDATE users SET total_tokens = total_tokens + ? WHERE uid = ?', (total, uid))
                return True
        except Exception as e:
            print(f"Token 日志失败: {e}")
            return False
