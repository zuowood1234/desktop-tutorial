#!/usr/bin/env python3
"""
清理无效回测数据
仅保留有效和有价值的文件
"""

import os
from pathlib import Path

# 项目根目录
BASE_DIR = Path('/Users/doriszuo/Documents/GitHub/desktop-tutorial')

# ============================================================================
# 应该保留的文件（有效的、重要的）
# ============================================================================
KEEP_FILES = {
    # 🟢 严格逐日回测（最新且正确的）
    'strict_daily_backtest.py',
    'strict_daily_backtest_results.csv',
    
    # 🟢 主要功能脚本（有用的工具）
    'batch_backtest_compare.py',  # 虽然有问题，但是代码保留用于学习
    'app.py',  # 主应用
    'database.py',
    
    # 🟢 分析报告和文档
    '严格逐日回测分析报告.md',
    '今日AI策略技术文档.md',
    'AI_Decision_Comparison_Analysis.md',
    'corrected_analysis.md',
    
    # 🟢 当前使用的配置
    '.env',
    'requirements.txt',
    'README.md',
    'requirement.md',
}

# ============================================================================
# 应该删除的文件（无效的、有数据泄露问题的）
# ============================================================================
DELETE_FILES = {
    # 🔴 昨日CSV回测结果（有数据泄露，不可信）
    'backtest_summary_advanced.csv',
    'backtest_details_advanced.csv',
    'backtest_details_annual.csv',
    'backtest_summary_primary.csv',
    'backtest_details_primary.csv',
    
    # 🔴 其他旧的回测结果
    'backtest_result.csv',
    'backtest_compare_summary.csv',
    'backtest_compare_details.csv',
    'backtest_compare_summary_annual.csv',
    'backtest_final_details.csv',
    'backtest_final_summary.csv',
    'backtest_v3_summary.csv',
    'combined_backtest_details.csv',
    
    # 🔴 单股票日志（过时）
    'backtest_log_002910.csv',
    'backtest_log_300620.csv',
    'backtest_log_600703.csv',
    'backtest_log_601698.csv',
    
    # 🔴 日志文件（临时）
    'backtest_advanced_log.out',
    'backtest_compare.log',
    'backtest_compare_fast.log',
    'backtest_stdout.log',
    'batch_backtest.log',
    
    # 🔴 测试脚本（临时分析用）
    'test_ai_reasoning.py',
    'compare_jan_2025.py',
    'compare_jan_2026_moonshot.py',
    'compare_strategy_returns.py',
    'compare_4_strategies.py',
    'analyze_csv_real_trades.py',
    'batch_vs_single_analysis.py',
    
    # 🔴 旧的回测脚本
    'backtest.py',
    'debug_backtest.py',
    'batch_backtest.py',
    'batch_backtest_compare_fast.py',
    'run_v3_backtest.py',
    'merge_backtest_results.py',
    
    # 🔴 测试目录中的旧结果
    'test/backtest_result.csv',
}

def main():
    print("="*80)
    print("🧹 清理无效回测数据")
    print("="*80)
    
    # 统计
    deleted = []
    kept = []
    not_found = []
    
    print("\n📋 将要删除的文件：")
    print("-"*80)
    
    for filename in sorted(DELETE_FILES):
        filepath = BASE_DIR / filename
        
        if filepath.exists():
            print(f"  🔴 {filename}")
            deleted.append(filename)
        else:
            not_found.append(filename)
    
    print(f"\n找到 {len(deleted)} 个文件可以删除")
    
    if not_found:
        print(f"\n⚠️  以下文件未找到（可能已删除）：")
        for f in not_found:
            print(f"  - {f}")
    
    # 确认
    print("\n" + "="*80)
    response = input("❓ 确认删除这些文件吗？(yes/no): ").strip().lower()
    
    if response == 'yes':
        print("\n🗑️  开始删除...")
        success_count = 0
        error_count = 0
        
        for filename in deleted:
            filepath = BASE_DIR / filename
            try:
                if filepath.is_file():
                    filepath.unlink()
                    print(f"  ✅ 已删除: {filename}")
                    success_count += 1
                elif filepath.is_dir():
                    import shutil
                    shutil.rmtree(filepath)
                    print(f"  ✅ 已删除目录: {filename}")
                    success_count += 1
            except Exception as e:
                print(f"  ❌ 删除失败: {filename} ({e})")
                error_count += 1
        
        print("\n" + "="*80)
        print(f"✅ 成功删除 {success_count} 个文件")
        if error_count > 0:
            print(f"❌ {error_count} 个文件删除失败")
        print("="*80)
        
        # 显示保留的重要文件
        print("\n📌 以下重要文件已保留：")
        print("-"*80)
        for filename in sorted(KEEP_FILES):
            filepath = BASE_DIR / filename
            if filepath.exists():
                if filepath.is_file():
                    size = filepath.stat().st_size
                    size_kb = size / 1024
                    print(f"  🟢 {filename:<50} ({size_kb:.1f} KB)")
                    kept.append(filename)
        
        print(f"\n保留了 {len(kept)} 个重要文件")
        
    else:
        print("\n❌ 取消删除操作")
    
    print("\n" + "="*80)
    print("🎯 清理完成！")
    print("="*80)
    print("""
重要提示：
1. ✅ 保留了严格逐日回测结果（无数据泄露）
2. ❌ 删除了昨日CSV回测结果（有数据泄露问题）
3. 🔄 如需重新回测，请使用 strict_daily_backtest.py
    """)

if __name__ == "__main__":
    main()
