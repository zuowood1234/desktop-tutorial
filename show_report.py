import pandas as pd
import sys

excel_file = "2025_Strategy_Grand_Battle.xlsx"
try:
    df_summary = pd.read_excel(excel_file, sheet_name="收益率大比拼")
    print("\n" + "="*80)
    print("🏆 2025年度 策略回测终极战报 (Summary)")
    print("="*80)
    print(df_summary.to_markdown(index=False))
except Exception as e:
    print(f"Failed to read file: {e}")
