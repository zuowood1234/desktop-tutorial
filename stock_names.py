import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# 股票代码到名称的映射（离线使用，由实时API同步）
STOCK_NAMES = {
    '002910': '庄园牧场', 
    '601698': '中国卫通', 
    '600703': '三安光电', 
    '300620': '光库科技', 
    '600745': '闻泰科技', 
    '002920': '德赛西威', 
    '002304': '洋河股份', 
    '601288': '农业银行', 
    '601126': '四方股份', 
    '600879': '航天电子', 
    '002905': '金逸影视', 
    '603598': '引力传媒', 
    '601881': '中国银河', 
    '603983': '丸美生物', 
    '605136': '丽人丽妆', 
    '600362': '江西銅業', 
    '688141': '杰华特', 
    '002284': '亚太股份', 
    '300115': '长盈精密', 
    '600276': '恒瑞医药', 
    '002717': 'ST岭南', 
    '002973': '侨银股份', 
    '001337': '四川黄金', 
    '601212': '白银有色', 
    '002456': '欧菲光', 
    '601138': '工业富联', 
    '002050': '三花智控', 
    '688207': '格灵深瞳', 
    '688041': '海光信息', 
    '688676': '金盘科技',
    '601318': '中国平安',
    '600519': '贵州茅台',
    '300456': '赛微电子',
    '002409': '雅克科技',
    '688981': '中芯国际'
}

CACHE_FILE = "stock_names_cache.json"

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except:
        pass

# 初始化加载缓存
DYNAMIC_CACHE = load_cache()

# AI 客户端初始化
API_KEY = os.getenv("DEEPSEEK_API_KEY")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
client = None
if API_KEY:
    try:
        client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    except:
        pass

def get_stock_name_offline(code):
    """
    智能获取股票名称（多级联动）：
    1. 内存/硬编码字典
    2. 本地缓存 (stock_names_cache.json)
    3. 【新增】Supabase 云端数据库 (实现全网同步)
    4. 【终极】直接问 AI (DeepSeek) -> 查到后自动同步到云端和本地
    """
    # 1. 优先查内存/硬编码
    if code in STOCK_NAMES:
        return STOCK_NAMES[code]
        
    # 2. 查本地动态缓存
    global DYNAMIC_CACHE
    if code in DYNAMIC_CACHE:
        return DYNAMIC_CACHE[code]
        
    # 3. 查 Supabase 云端表 (实现不同端同步)
    from database import DBManager
    from sqlalchemy import text
    try:
        db = DBManager()
        with db._get_connection() as conn:
            query = text("SELECT name FROM stock_info WHERE code = :c")
            result = conn.execute(query, {"c": code}).fetchone()
            if result:
                name = result[0]
                # 同步到本地内存缓存，加速后续访问
                DYNAMIC_CACHE[code] = name
                return name
    except Exception as e:
        # print(f"Cloud fetch name error: {e}")
        pass

    # 4. 询问 AI (终极方案)
    if client:
        try:
            print(f"🤖 正在询问 AI 获取股票名称: {code}...")
            prompt = f"请直接告诉我 A股代码 {code} 的股票中文简称是什么？不要废话，只回答名字（例如：贵州茅台）。如果不确定或不存在，回答UNKNOWN。"
            
            resp = client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            name = resp.choices[0].message.content.strip()
            
            import re
            name = re.sub(r'[。，. \n]', '', name)
            
            if name and "UNKNOWN" not in name and len(name) < 10:
                # A. 存入本地内存和文件
                DYNAMIC_CACHE[code] = name
                save_cache(DYNAMIC_CACHE)
                
                # B. 【新增】同步到云端数据库，供互联网端使用
                try:
                    db = DBManager()
                    with db._get_connection() as conn:
                        upsert_sql = text("INSERT INTO stock_info (code, name) VALUES (:c, :n) ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name")
                        conn.execute(upsert_sql, {"c": code, "n": name})
                        conn.commit()
                except:
                    pass
                    
                return name
        except Exception as e:
            print(f"AI fetch name error: {e}")
            pass

    # 5. 兜底返回代码
    return code
