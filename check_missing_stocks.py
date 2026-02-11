import pandas as pd
import akshare as ak
import sys
import subprocess
import os

# 1. 期望列表 (26只)
EXPECTED_CODES = [
    "000960", "002284", "002409", "002517", "002905", "002910", 
    "300102", "300115", "300274", "300442", "300456", "300620", 
    "300857", "301171", "600362", "600703", "600745", "600879", 
    "601126", "601698", "603308", "603598", "605136", "688141", 
    "688536", "688981"
]

EXCEL_FILE = "2025_Final_Strategy_Report.xlsx"

print("🕵️‍♂️ 开始核对回测结果完整性...")

# 2. 读取现有结果
if not os.path.exists(EXCEL_FILE):
    print("❌ Excel 文件不存在！")
    sys.exit(1)

df_result = pd.read_excel(EXCEL_FILE, sheet_name="策略收益对比总表")
# 假设 'Code' 列通常是第一列，或者名字叫 '代码'
# 为了兼容性，先把第一列强制转为字符串并比较
df_result.iloc[:, 0] = df_result.iloc[:, 0].astype(str).str.zfill(6)
FOUND_CODES = df_result.iloc[:, 0].tolist()

missing_codes = []
for code in EXPECTED_CODES:
    if code not in FOUND_CODES:
        missing_codes.append(code)

if not missing_codes:
    print("✅ 完美！26只股票全部都在。")
else:
    print(f"❌ 发现 {len(missing_codes)} 只股票缺失！")
    print(f"缺失名单: {missing_codes}")
    
    # 3. 诊断缺失原因
    print("\n🩺 开始诊断缺失股票...")
    for code in missing_codes:
        print(f"正在检查 {code} 的数据源...")
        try:
            # 尝试直接调用 akshare
            df = ak.stock_zh_a_hist(symbol=code, period="daily", start_date="20250101", end_date="20250110", adjust="qfq")
            if df.empty:
                print(f"   ⚠️ {code}: Akshare 返回数据为空 (可能停牌/未上市/代码错误)")
            else:
                print(f"   ✅ {code}: 数据源正常。可能是回测脚本Bug。尝试单跑 V1...")
                # 尝试单跑一次 V1 看看报错
                try:
                    res = subprocess.run([sys.executable, "backtest_engine.py", code, "--start", "2025-01-01", "--end", "2025-12-31"], 
                                   capture_output=True, text=True)
                    if res.returncode != 0:
                         print(f"   ❌ V1 运行报错: {res.stderr[:200]}")
                    else:
                         print(f"   ✅ V1 运行成功。说明是 Runner 的合并逻辑问题。")
                except Exception as e:
                    print(f"   ❌ V1 调用异常: {e}")

        except Exception as e:
            print(f"   ❌ {code}: Akshare 接口报错: {e}")

print("\n🏁 诊断完成。")
