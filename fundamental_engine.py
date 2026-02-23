import os
import pandas as pd
import numpy as np
import akshare as ak
import warnings
import time
warnings.filterwarnings('ignore')

SUPER_VAULT_DIR = "backtest_data/super_vault"
FUNDAMENTAL_VAULT_DIR = "backtest_data/final_vault"
os.makedirs(FUNDAMENTAL_VAULT_DIR, exist_ok=True)

def fetch_and_merge_fundamentals(df, code):
    """
    获取单只股票的财务和估值指标 (D表)，并通过严谨的 Announcement Date 映射方法，
    与已经包含C表指标的日线大表无缝对接！
    """
    print(f"    --> 正在拉取 [{code}] 估值指标库...")
    
    # 策略 1. 每日估值指标 (PE, PB, 总市值, 流通市值等)
    # Akshare 的 stock_a_lg_indicator() 能拿到个股从上市以来的每日估值指标 (非常强大，无需财报对齐)
    # 包含：pe_ttm, pb, total_mv, dv_ratio(股息率)
    try:
        val_df = ak.stock_value_em(symbol=code)
        if not val_df.empty:
            val_df['Date'] = pd.to_datetime(val_df['数据日期'])
            # 提取有用列并重命名
            val_cols_rename = {
                'PE(TTM)': 'PE_TTM',
                '市净率': 'PB',
                '总市值': 'Total_MV',       # 总市值
            }
            # akshare 有些版本列名会有中英文混杂，这里做防御性提取
            available_cols = [c for c in val_cols_rename.keys() if c in val_df.columns]
            val_df = val_df[['Date'] + available_cols].rename(columns=val_cols_rename)
            
            # 衍生因子: PE 历史分位数 (PE_Percentile) 
            # 这里的计算要求用过去3年的滚动数据求分位，为了性能和数据完整性，我们直接算全部历史的滚动百分位
            if 'PE_TTM' in val_df.columns:
                # 滚动计算过去 750个交易日 (约3年) 的 PE分位数
                val_df['PE_Percentile_3Y'] = val_df['PE_TTM'].rolling(window=750, min_periods=250).apply(
                    lambda x: (pd.Series(x).rank(pct=True).iloc[-1]) * 100, raw=False
                )
            
            # 使用 left join 基于 Date 拼接到传进来的主表 df 上
            df = pd.merge(df, val_df, on='Date', how='left')
    except Exception as e:
        print(f"      [!] 获取估值数据失败: {e}")

    # 策略 2. 定期财报指标 (ROE，净利润增速等)
    # 这里是防死未来函数的重灾区！我们必须要用"公告日期 (Actual Announcement Date)" 为基准！
    print(f"    --> 正在拉取 [{code}] 财务报表基因...")
    try:
        # 获取个股的财务摘要 
        # stock_financial_abstract_ths 包含 ROE 等，但我们需要日期映射
        fin_df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
        if not fin_df.empty and '报告期' in fin_df.columns:
            # 数据清洗：很多列名叫'净资产收益率'，带有百分号
            # 我们需要提取：报告期, 净资产收益率, 净利润同比增长率, 营业总收入同比增长率
            # 但这些字段没有披露日期(公告日)，只有报告期(比如 3-31, 6-30)，
            # 真实 A股 中，一季报最晚在4月30日，中报最晚在8月31日，三季报最晚在10月31日，年报最晚在次年4月30日公布。
            # 为了防止未来函数，如果我们拿不到真实的精确公告日，我们必须采取【最保守的极限推迟法 (Worst-Case Delay)】
            
            fin_df['Report_Date'] = pd.to_datetime(fin_df['报告期'])
            
            def get_conservative_announce_date(report_date):
                # Q1 (3-31) -> 必须等到 4-30 才认为财报已全市场公开可用
                if report_date.month == 3:
                     return report_date.replace(month=4, day=30)
                # Q2 (6-30) -> 必须等到 8-31 
                elif report_date.month == 6:
                     return report_date.replace(month=8, day=31)
                # Q3 (9-30) -> 必须等到 10-31
                elif report_date.month == 9:
                     return report_date.replace(month=10, day=31)
                # Q4/年报 (12-31) -> A股年报最晚 4-30
                elif report_date.month == 12:
                     return report_date.replace(year=report_date.year+1, month=4, day=30)
                return report_date
                
            fin_df['Announce_Date'] = fin_df['Report_Date'].apply(get_conservative_announce_date)
            # 因为停牌或周末的原因，财报公告日不一定是交易日，我们需要将它和我们大表的 Date 对齐。
            
            # 清洗字符串数字 (例如去除 "15.34%" 中的 % 并转 float)
            def clean_pct(val):
                if isinstance(val, str):
                    if val == '--' or val == '': return np.nan
                    return float(val.replace('%', ''))
                return float(val)

            # 提取指标
            target_metrics = {}
            if '净资产收益率' in fin_df.columns:
                target_metrics['ROE'] = fin_df['净资产收益率'].apply(clean_pct)
            if '净利润同比增长率' in fin_df.columns:
                target_metrics['NetProfit_YOY'] = fin_df['净利润同比增长率'].apply(clean_pct)
            if '扣非净利润同比增长率' in fin_df.columns:
                target_metrics['DeductedNetProfit_YOY'] = fin_df['扣非净利润同比增长率'].apply(clean_pct)
            if '营业总收入同比增长率' in fin_df.columns:
                target_metrics['Revenue_YOY'] = fin_df['营业总收入同比增长率'].apply(clean_pct)
            if '资产负债率' in fin_df.columns:
                target_metrics['Debt_Ratio'] = fin_df['资产负债率'].apply(clean_pct)

            fin_metrics_df = pd.DataFrame(target_metrics)
            fin_metrics_df['Announce_Date'] = fin_df['Announce_Date']
            
            # 排序并清除重复的公告日期 (如果有财报更正等情况)
            fin_metrics_df = fin_metrics_df.sort_values('Announce_Date').drop_duplicates(subset=['Announce_Date'], keep='last')
            
            # ---- 绝杀：As-of Merge (基于时间线的安全对齐) ----
            # 我们拿主表 df(每一天) 去匹配 fin_metrics_df 里在这一天之前（含这一天）所发布的【最近一份报表】
            # 这个操作在 pandas 叫 merge_asof，是用来做量化的绝对神器，完美断绝任何时空穿越
            
            # 提取 df 里已有的日期列
            df_dates = df[['Date']].sort_values('Date')
            
            # 用 merge_asof 抓取最近的财报
            asof_df = pd.merge_asof(
                df_dates, 
                fin_metrics_df.dropna(subset=['Announce_Date']).sort_values('Announce_Date'), 
                left_on='Date', 
                right_on='Announce_Date', 
                direction='backward' # 意味着：对于任意一天，向后倒退去寻找最近的一次发布日期的数据
            )
            # 将抓出来的财报列并入主 df
            for col in target_metrics.keys():
                 if col in asof_df.columns:
                     df[col] = asof_df[col]
                     
    except Exception as e:
        print(f"      [!] 获取财务报表数据失败或该股无数据: {e}")

    # 对于 df 里因为早期或者未发布时填充的 NaN 财务数据，不用理会，回测查询时自动过滤
    return df

def build_final_fundamental_vault():
    """读取包含 C表的 Super Parquet，融合 D表，生成终极的 Final_Vault"""
    files = [f for f in os.listdir(SUPER_VAULT_DIR) if f.endswith('.parquet')]
    print(f"检测到 {len(files)} 个超级技术表，正在灌入基本面 D 表...")

    for f in files:
        base_path = os.path.join(SUPER_VAULT_DIR, f)
        final_path = os.path.join(FUNDAMENTAL_VAULT_DIR, f)
        code = f.replace(".parquet", "")
        
        # 1. 读取包含技术指标的 C 表
        df = pd.read_parquet(base_path)
        
        # 2. 拉取 D 并且防未来合并
        final_df = fetch_and_merge_fundamentals(df, code)
        
        # 3. 存储为终极的满配大表 (Final Vault)
        final_df.to_parquet(final_path, engine="pyarrow", index=False)
        print(f"  [√ 完工] {f} 财报基本面注入完成！最终列数爆炸级达到：{len(final_df.columns)}")
        time.sleep(1.5) # 防止Akshare封禁

if __name__ == "__main__":
    print("\n=== Final Vault 财务基本面合并引擎启动 ===")
    build_final_fundamental_vault()
    print("\n所有底层数据 100% 构建完毕！随时可以进入前端 UI 与回测阶段！")
