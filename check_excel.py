import pandas as pd
import os

excel_file = "2025_Final_Strategy_Report.xlsx"

print(f"🔍 正在寻找文件: {os.path.abspath(excel_file)}")

if os.path.exists(excel_file):
    print("✅ 文件存在！")
    try:
        df = pd.read_excel(excel_file, sheet_name="策略收益对比总表")
        print("\n📊 文件内容预览 (前5行):")
        print(df.head().to_markdown(index=False))
    except Exception as e:
        print(f"❌ 读取错误: {e}")
else:
    print("❌ 文件找不到了！我也很懵圈。")

# 列出当前目录下所有的xlsx文件，看看有没有名字相近的
print("\n📂 当前目录下的所有 XLSX 文件:")
import glob
for f in glob.glob("*.xlsx"):
    print(f" - {f}")
