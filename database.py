
import os
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from psycopg2.extensions import register_adapter, AsIs

# 注册 numpy int64 适配器，防止 psycopg2 报错
register_adapter(np.int64, AsIs)

# 加载 .env 确保获取到 DATABASE_URL
load_dotenv()

class DBManager:
    def __init__(self):
        # 优先读取 DATABASE_URL，无需本地路径
        self.db_url = os.getenv("DATABASE_URL")
        if not self.db_url:
            raise ValueError("DATABASE_URL environment variable is not set!")
        
        # 兼容性处理：SQLAlchemy 需要 postgresql:// 开头
        if self.db_url.startswith("postgres://"):
            self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            
        # 🔧 增强的连接池配置，防止 SSL EOF 错误
        self.engine = create_engine(
            self.db_url,
            pool_pre_ping=True,          # 使用前测试连接是否有效
            pool_recycle=600,             # 10分钟回收连接（防止空闲超时）
            pool_size=5,                  # 连接池大小
            max_overflow=10,              # 最大溢出连接数
            connect_args={
                "sslmode": "require",      # 强制启用 SSL，解决云端连接报错
                "connect_timeout": 10,    # 连接超时
                "keepalives": 1,          # 启用TCP keepalive
                "keepalives_idle": 30,    # 30秒后发送keepalive
                "keepalives_interval": 10,# keepalive间隔
                "keepalives_count": 5     # 重试次数
            }
        )
        
    def _get_connection(self):
        """获取数据库连接（带自动重试）"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return self.engine.connect()
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(0.5 * (attempt + 1))  # 指数退避
                    continue
                else:
                    raise  # 最后一次失败则抛出异常

    # --- 用户管理 ---
    def register_user(self, username, email, password, role='user'):
        """注册新用户"""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        # admin 默认有权限
        can_backtest = True if role.lower() == 'admin' else False
        
        try:
            with self._get_connection() as conn:
                # 使用 SQLAlchemy text() 绑定参数
                conn.execute(
                    text('INSERT INTO users (username, email, password_hash, role, status, can_backtest) VALUES (:u, :e, :p, :r, :s, :c)'), 
                    {"u": username, "e": email, "p": pw_hash, "r": role, "s": 'active', "c": can_backtest}
                )
                conn.commit()
                return True, "注册成功"
        except Exception as e:
            err_msg = str(e)
            if 'username' in err_msg or 'users_username_key' in err_msg: return False, "用户名已存在"
            if 'email' in err_msg or 'users_email_key' in err_msg: return False, "该邮箱已被注册"
            return False, f"注册失败: {err_msg}"

    def login_user(self, username, password):
        """验证登录并在状态正常时返回用户信息"""
        pw_hash = hashlib.sha256(password.encode()).hexdigest()
        with self._get_connection() as conn:
            result = conn.execute(
                text('SELECT uid, username, email, role, status, can_backtest FROM users WHERE username = :u AND password_hash = :p'), 
                {"u": username, "p": pw_hash}
            )
            user = result.fetchone() # returns Row or None
            
            if user:
                # SQLAlchemy web Row 转 dict
                user_dict = user._mapping
                user_dict = dict(user_dict)
                
                if user_dict['status'] != 'active':
                    return "disabled"
                
                # Postgres boolean 无需转换，已经是 True/False
                return user_dict
            return None

    def get_all_users(self):
        """管理员特权：获取所有用户信息（包含Token统计）"""
        with self._get_connection() as conn:
            return pd.read_sql_query('SELECT uid, username, email, role, status, can_backtest, total_tokens, created_at FROM users', conn)

    def update_user_status(self, uid, new_status):
        """管理员特权：禁用/启用用户"""
        with self._get_connection() as conn:
            conn.execute(text('UPDATE users SET status = :s WHERE uid = :id'), {"s": new_status, "id": uid})
            conn.commit()

    def update_user_backtest_permission(self, uid, can_backtest):
        """管理员特权：授权/取消回测权限"""
        with self._get_connection() as conn:
            # Postgres boolean
            val = True if can_backtest else False
            conn.execute(text('UPDATE users SET can_backtest = :b WHERE uid = :id'), {"b": val, "id": uid})
            conn.commit()

    # --- 自选股与标签管理 ---
    def add_to_watchlist(self, uid, stock_code, tag='未分类'):
        """添加股票到自选，带标签 (PG 使用 ON CONFLICT 处理 REPLACE)"""
        try:
            with self._get_connection() as conn:
                # PostgreSQL 没有 INSERT OR REPLACE，使用 ON CONFLICT DO UPDATE
                sql = """
                INSERT INTO watchlist (uid, stock_code, tag) 
                VALUES (:uid, :code, :tag)
                ON CONFLICT (uid, stock_code) 
                DO UPDATE SET tag = EXCLUDED.tag
                """
                conn.execute(text(sql), {"uid": uid, "code": stock_code, "tag": tag})
                conn.commit()
                return True
        except Exception as e:
            print(f"添加失败: {e}")
            return False

    def remove_from_watchlist(self, uid, stock_code):
        """从自选移除"""
        with self._get_connection() as conn:
            conn.execute(text('DELETE FROM watchlist WHERE uid = :uid AND stock_code = :code'), {"uid": uid, "code": stock_code})
            conn.commit()

    def get_user_watchlist(self, uid):
        """获取用户的所有自选股"""
        # pd.read_sql_query 支持 SQLAlchemy engine/connection
        with self._get_connection() as conn:
            query = "SELECT stock_code, tag FROM watchlist WHERE uid = %(uid)s"
            # Pandas read_sql 使用 %s 风格或者 params 字典
            return pd.read_sql_query(query, conn, params={"uid": uid})

    def get_tags(self, uid):
        """获取用户已创建的所有唯一标签"""
        with self._get_connection() as conn:
            result = conn.execute(text('SELECT DISTINCT tag FROM watchlist WHERE uid = :uid'), {"uid": uid})
            return [row[0] for row in result.fetchall()]

    def update_stock_tag(self, uid, stock_code, new_tag):
        """更新已有股票的标签"""
        with self._get_connection() as conn:
            conn.execute(
                text('UPDATE watchlist SET tag = :tag WHERE uid = :uid AND stock_code = :code'), 
                {"tag": new_tag, "uid": uid, "code": stock_code}
            )
            conn.commit()

    # --- 每日建议存储 ---
    def save_daily_recommendation(self, uid, stock_code, date, tech_res, sent_res, price):
        """保存每日自动生成的建议"""
        try:
            with self._get_connection() as conn:
                # 同样使用 ON CONFLICT 替代 INSERT OR REPLACE
                sql = """
                    INSERT INTO daily_recommendations 
                    (uid, stock_code, date, tech_action, tech_reason, sent_action, sent_reason, price)
                    VALUES (:uid, :code, :date, :ta, :tr, :sa, :sr, :price)
                    ON CONFLICT (uid, stock_code, date)
                    DO UPDATE SET 
                        tech_action = EXCLUDED.tech_action,
                        tech_reason = EXCLUDED.tech_reason,
                        sent_action = EXCLUDED.sent_action,
                        sent_reason = EXCLUDED.sent_reason,
                        price = EXCLUDED.price
                """
                conn.execute(text(sql), {
                    "uid": uid, "code": stock_code, "date": date, 
                    "ta": tech_res['action'], "tr": tech_res['reason'],
                    "sa": sent_res['action'], "sr": sent_res['reason'],
                    "price": price
                })
                conn.commit()
                return True
        except Exception as e:
            print(f"保存每日建议失败: {e}")
            return False

    def get_daily_recommendations(self, uid, date=None):
        """获取历史建议，如果提供日期则查询特定日期"""
        with self._get_connection() as conn:
            if date:
                # 注意：pd.read_sql 最好用 %(name)s 风格传参
                query = "SELECT * FROM daily_recommendations WHERE uid = %(uid)s AND date = %(date)s ORDER BY created_at DESC"
                return pd.read_sql_query(query, conn, params={"uid": uid, "date": date})
            else:
                query = "SELECT DISTINCT date FROM daily_recommendations WHERE uid = %(uid)s ORDER BY date DESC"
                return pd.read_sql_query(query, conn, params={"uid": uid})

    def get_recommendations_by_date(self, uid, date):
        """获取特定日期的所有建议"""
        with self._get_connection() as conn:
            query = "SELECT * FROM daily_recommendations WHERE uid = %(uid)s AND date = %(date)s"
            return pd.read_sql_query(query, conn, params={"uid": uid, "date": date})
            
    def log_token_usage(self, uid, action_type, stock_code, prompt, completion):
        """记录并累加用户的 token 消耗"""
        total = prompt + completion
        try:
            with self._get_connection() as conn:
                # 1. 记录明细
                conn.execute(
                    text('''
                        INSERT INTO token_logs (uid, action_type, stock_code, prompt_tokens, completion_tokens, total_tokens)
                        VALUES (:uid, :type, :code, :pt, :ct, :tt)
                    '''), 
                    {"uid": uid, "type": action_type, "code": stock_code, "pt": prompt, "ct": completion, "tt": total}
                )
                
                # 2. 累加到用户主表
                conn.execute(
                    text('UPDATE users SET total_tokens = total_tokens + :tt WHERE uid = :uid'), 
                    {"tt": total, "uid": uid}
                )
                conn.commit()
                return True
        except Exception as e:
            print(f"Token 日志失败: {e}")
            return False
