import requests
import akshare as ak
import time

# 内存缓存，避免重复请求
NAME_CACHE = {}

def get_stock_name(code):
    """
    通过多重数据源获取股票实时名称 (双重验证)
    优先级: 缓存 -> 新浪实时接口 -> 东财个股资料 -> 原始代码
    """
    # 1. 检查缓存
    if code in NAME_CACHE:
        return NAME_CACHE[code]
    
    name = None
    
    # 2. 数据源 A: 新浪财经 (极速, 实时)
    try:
        market = 'sh' if code.startswith('6') else 'sz'
        url = f"http://hq.sinajs.cn/list={market}{code}"
        headers = {
            'Referer': 'https://finance.sina.com.cn/',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            # 新浪返回的是 GBK 编码
            text = response.content.decode('gbk')
            # 格式: var hq_str_sh603778="国旅联合,..."
            if '="' in text:
                content = text.split('="')[1]
                if len(content) > 1:
                    name_part = content.split(',')[0]
                    if name_part and len(name_part.strip()) > 0:
                        name = name_part.strip()
    except Exception as e:
        print(f"Sina api failed for {code}: {e}")

    # 3. 数据源 B: AkShare / 东财 (权威, 备选)
    # 如果新浪失败，或者双重验证需求(这里作为Failover更合适，因为Sina已经很快了)
    if not name:
        try:
            # 获取个股信息
            df = ak.stock_individual_info_em(symbol=code)
            # 查找 "股票简称"
            for _, row in df.iterrows():
                if row['item'] == '股票简称':
                    name = row['value']
                    break
        except Exception as e:
            print(f"Akshare api failed for {code}: {e}")

    # 4. 结果处理
    if name:
        NAME_CACHE[code] = name
        return name
    else:
        return code # 没找到就返回代码本身

# 兼容旧函数名，方便迁移
def get_stock_name_offline(code):
    return get_stock_name(code)
