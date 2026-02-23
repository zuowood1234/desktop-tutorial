import os
import pandas as pd
import numpy as np
from ashare_broker import AShareBroker

class StrategyRunner:
    """
    负责驱动回测进程的“司令部”。
    它将静态的 Super_Parquet 转化为按天推进的序列，
    每天计算交易信号，并指挥 AShareBroker 执行买卖。
    最终生成所有统计指标和对齐的资金曲线表。
    """
    def __init__(self, data_path, initial_cash=200000, 
                 commission=0.00025, stamp_duty=0.0005, slippage=0.001,
                 buy_logic=None, sell_logic=None,
                 stop_loss_pct=None, take_profit_pct=None, max_hold_days=None,
                 start_date=None, end_date=None):
        """
        :param data_path: 要回测的个股的 Super Parquet 文件绝对路径
        :param buy_logic: 字符串格式的 Pandas query 表达式 (例如: "MA_5 > MA_10 and MACD > 0")
        :param sell_logic: 同上
        :param stop_loss_pct: 止损百分比 (例如 0.08 表示跌去 8% 强制平仓)
        :param max_hold_days: 最长持股天数，超过则不论盈亏强制卖出
        """
        self.df = pd.read_parquet(data_path)
        self.df['Date'] = pd.to_datetime(self.df['Date'])
        # 必须剔除延伸到未来还未发生日期的占位符日历（剔除掉大于今天的日期）
        self.df = self.df[self.df['Date'] <= pd.Timestamp.today()].copy()
        
        # 处理时间窗口过滤
        if start_date:
            self.df = self.df[self.df['Date'] >= pd.to_datetime(start_date)].copy()
        if end_date:
            self.df = self.df[self.df['Date'] <= pd.to_datetime(end_date) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)].copy()
            
        self.df = self.df.sort_values("Date").reset_index(drop=True)
        
        self.broker = AShareBroker(initial_cash, commission, stamp_duty, slippage)
        
        # 策略规则
        self.buy_logic = buy_logic
        self.sell_logic = sell_logic
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.max_hold_days = max_hold_days
        
        # 状态机追踪器
        self.holding_days = 0
        self.cost_price = 0.0
        
        # 回测结果存储
        self.equity_curve = [] # 每天的净值记录 [Date, Cash, Total_Value, Returns...]

    def _eval_condition(self, current_row, logic_str):
        """
        由于我们需要在逐行循环中执行 Pandas query 风格的逻辑，
        这里使用 Python 原生的 eval 将该行数据转化为字典进行判断。
        """
        if not logic_str or str(logic_str).strip() == "":
            return False
            
        # 将 Pandas 单行转为字典，供 eval 环境使用
        row_dict = current_row.to_dict()
        
        # 将 Pandas 的 "MA_5 > MA_10" 转化为安全可执行的代码
        # 注意：对于复杂表达式，这是个简化版执行器。如果逻辑极度复杂，
        # 实战中可以在循环外用 df.eval(logic_str) 算出一个布尔列，然后每天直接查那个布尔列。
        # 为了性能和绝对安全，我们在这里采取**预结算方案**！
        return row_dict.get("__VIRTUAL_SIGNAL__", False)

    def pre_calculate_signals(self):
        """
        性能优化核心：在行情开始前，一次性计算出全局的买卖信号！
        这样在抛给引擎跑耗时的大循环时，每天只需要查一个布尔值即可。
        """
        # 计算基础买入信号
        if self.buy_logic:
            try:
                self.df['__BUY_SIGNAL__'] = self.df.eval(self.buy_logic)
            except Exception as e:
                print(f"买入条件解析失败: {e}")
                self.df['__BUY_SIGNAL__'] = False
        else:
            self.df['__BUY_SIGNAL__'] = False
            
        # 计算基础卖出信号
        if self.sell_logic:
            try:
                self.df['__SELL_SIGNAL__'] = self.df.eval(self.sell_logic)
            except Exception as e:
                print(f"卖出条件解析失败: {e}")
                self.df['__SELL_SIGNAL__'] = False
        else:
            self.df['__SELL_SIGNAL__'] = False

    def run(self, action_timing="close"):
        """
        开始运行跨越历史的逐日回测
        :param action_timing: "close" 表示尾盘买入(使用收盘价), "open" 表示次日开盘买入
        """
        self.pre_calculate_signals()
        print(f"🔄 启动回测引擎大循环... 区间: {self.df['Date'].min().date()} 至 {self.df['Date'].max().date()}")
        
        n_days = len(self.df)
        
        for i in range(n_days):
            row = self.df.iloc[i]
            date = row['Date']
            is_trading = row['is_trading']
            
            # 第一件事：如果今天是有效交易日，同步价格给 Broker（用于停牌日净值继承）
            if is_trading:
                self.broker.record_last_price(row['Close_Raw'])
                
            # 第二件事：解除昨日买单的 T+1 锁定
            self.broker.daily_update_t1_lock()
            
            # 第三件事：资产净值清点
            # 即使今天停牌，也需要记录净值 (依靠 last_price)
            current_close = row['Close_Raw']
            current_equity = self.broker.evaluate_portfolio(current_close)
            
            # --- 以下是核心交易决策区 ---
            # 只有在正常交易日且存在有效价格，我们才进行决策
            if is_trading and not pd.isna(current_close):
                
                # 情况A: 当前已持有仓位 -> 判断是否触发卖出信条
                if self.broker.total_shares > 0:
                    self.holding_days += 1
                    
                    # 1. 检查风控刹车线 (止损 / 止盈)
                    triggered_sell = False
                    sell_reason = ""
                    current_return_pct = (current_close - self.cost_price) / self.cost_price
                    
                    if self.stop_loss_pct is not None and current_return_pct <= -abs(self.stop_loss_pct):
                        triggered_sell = True
                        sell_reason = "触碰固定止损线"
                    elif self.take_profit_pct is not None and current_return_pct >= abs(self.take_profit_pct):
                        triggered_sell = True
                        sell_reason = "触碰浮动止盈线"
                    elif self.max_hold_days is not None and self.holding_days >= self.max_hold_days:
                        triggered_sell = True
                        sell_reason = "持仓达到最长期限强制调仓"
                    elif row['__SELL_SIGNAL__']: # 策略逻辑产生的卖点
                        triggered_sell = True
                        sell_reason = "策略逻辑触发卖点"

                    if triggered_sell:
                        # 尝试执行全仓抛售
                        # 如果是触发了尾盘卖出
                        success, msg = self.broker.submit_sell_order(
                            date=date, 
                            trigger_price=row['Close_Raw'], 
                            limit_down_price=row['limit_down'], 
                            current_low=row['Low_Raw']
                        )
                        if success:
                            # 卖出成功，重置持仓状态机
                            self.holding_days = 0
                            self.cost_price = 0.0
                            # 特别提醒：今天卖完后，手里的钱变多了，要重新算一下今天的净值
                            current_equity = self.broker.evaluate_portfolio(row['Close_Raw'])
                        else:
                            # 卖出失败 (比如被跌停封死锁住了)，明天继续挨刀
                            pass
                            
                # 情况B: 当前空仓 -> 判断是否触发买入信条
                elif self.broker.total_shares == 0:
                    if row['__BUY_SIGNAL__']:
                        # 尝试执行全仓买入
                        # 这里假装执行“尾盘买入”策略
                        success, msg = self.broker.submit_buy_order(
                            date=date, 
                            trigger_price=row['Close_Raw'], 
                            limit_up_price=row['limit_up'], 
                            current_high=row['High_Raw']
                        )
                        if success:
                            # 记录建仓成本
                            self.cost_price = row['Close_Raw'] * (1 + self.broker.slippage)
                            self.holding_days = 1
                            current_equity = self.broker.evaluate_portfolio(row['Close_Raw'])

            # 将今日账户快照压入履历 (无论是否停牌)
            self.equity_curve.append({
                "Date": date,
                "Equity": current_equity,
                "Cash": self.broker.cash,
                "Position_Value": current_equity - self.broker.cash,
                "Is_Trading": is_trading,
                "Close_Price": current_close
            })

        print("🚦 回测引擎大循环结束！")
        return pd.DataFrame(self.equity_curve), self.broker.trades

    def generate_report(self, equity_df):
        """生成专业战报 (夏普，回撤，胜率等)"""
        # 2.5 算出基准收益率 (Benchmark Return: 市场死拿真实收益率)
        # 前复权价格在常年分红的股票上可能出现负数，导致 (p_end - p_start)/p_start 失真。
        # 最精确的做法是将无滑点的每日真实涨跌幅 Pct_Chg_Raw 组合复利。
        valid_df = self.df[self.df['is_trading'] == True]
        if not valid_df.empty and 'Pct_Chg_Raw' in valid_df.columns:
            benchmark_return = (1 + valid_df['Pct_Chg_Raw'] / 100.0).prod() - 1
        else:
            benchmark_return = 0.0
            
        init_eq = self.broker.initial_cash
        
        # 如果从头到尾没有资金变化，说明未交易，直接返回空战果
        if len(self.broker.trades) == 0:
            return {
                "Initial_Cash": init_eq,
                "Final_Equity": init_eq,
                "Total_Return": 0.0,
                "Benchmark_Return": benchmark_return,
                "Annual_Return": 0.0,
                "Max_Drawdown": 0.0,
                "Sharpe_Ratio": 0.0,
                "Calmar_Ratio": 0.0,
                "Total_Trades_Pairs": 0,
                "Win_Rate": 0.0,
                "Tear_Sheet_Yearly": pd.DataFrame(),
                "Tear_Sheet_Monthly": pd.DataFrame()
            }

        # 1. 计算日度收益率序列
        equity_df['Daily_Return'] = equity_df['Equity'].pct_change().fillna(0)
        
        # 2. 基础收益数据
        final_eq = equity_df['Equity'].iloc[-1]
        total_return = (final_eq - init_eq) / init_eq
        
        # 3. 最大回撤 (用极简又高效的 Pandas 算法)
        running_max = equity_df['Equity'].cummax()
        drawdown = (equity_df['Equity'] - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # 4. 年化相关 (假设一年 250 个交易日)
        # 交易日总数
        trading_days = len(equity_df[equity_df['Is_Trading'] == True])
        # 避免分母为0或负数开方
        if trading_days > 0:
            annual_return = (1 + total_return) ** (250 / trading_days) - 1
        else:
            annual_return = 0

        # 夏普比率 (无风险利率设为3%)
        daily_rf = 0.03 / 250
        excess_returns = equity_df['Daily_Return'] - daily_rf
        sharpe = 0
        if excess_returns.std() != 0:
            sharpe = (excess_returns.mean() / excess_returns.std()) * np.sqrt(250)

        # 卡玛比率 (Calmar)
        calmar = 0
        if max_drawdown < 0:
            calmar = annual_return / abs(max_drawdown)

        # 5. 胜率与交易统计
        trades_df = pd.DataFrame(self.broker.trades)
        win_trades = 0
        total_closed_trades = 0
        
        if not trades_df.empty:
            # 配对买卖来计算胜率
            buys = trades_df[trades_df['Type'] == 'BUY']
            sells = trades_df[trades_df['Type'] == 'SELL']
            
            for i in range(min(len(buys), len(sells))):
                total_closed_trades += 1
                b_price = buys.iloc[i]['Price']
                s_price = sells.iloc[i]['Price']
                # 含滑点和手续费后的盈亏判断更为真实，这里简化判断为卖出单价 > 买入单价
                if s_price > b_price:
                    win_trades += 1
                    
        win_rate = win_trades / total_closed_trades if total_closed_trades > 0 else 0
        
        # 6. 计算 Tear Sheet (分年/分月截面对比)
        tear_sheet_yearly = []
        tear_sheet_monthly = []
        
        if 'Close_Price' in equity_df.columns:
            equity_df['Year'] = equity_df['Date'].dt.year
            equity_df['Month'] = equity_df['Date'].dt.to_period('M')
            
            def calc_metrics(df_slice, period_name):
                if len(df_slice) < 2: return None
                start_eq = df_slice['Equity'].iloc[0]
                end_eq = df_slice['Equity'].iloc[-1]
                strat_ret = (end_eq - start_eq) / start_eq if start_eq > 0 else 0
                
                # 处理可能包含 NaN 的 Close_Price 序列
                valid_prices = df_slice['Close_Price'].dropna()
                if len(valid_prices) >= 2:
                    start_p = float(valid_prices.iloc[0])
                    end_p = float(valid_prices.iloc[-1])
                    bench_ret = (end_p - start_p) / start_p if start_p != 0 else 0
                else:
                    bench_ret = 0
                    
                alpha = strat_ret - bench_ret
                r_max = df_slice['Equity'].cummax()
                mdd = ((df_slice['Equity'] - r_max) / r_max).min()
                
                return {
                    "周期": period_name,
                    "策略净收益": strat_ret,
                    "基准天然涨幅": bench_ret,
                    "🔥 超额收益 (Alpha)": alpha,
                    "期间最大回撤": mdd
                }
                
            for year, group in equity_df.groupby('Year'):
                res = calc_metrics(group, f"{year}年")
                if res: tear_sheet_yearly.append(res)
                
            for month, group in equity_df.groupby('Month'):
                res = calc_metrics(group, str(month))
                if res: tear_sheet_monthly.append(res)
        
        report = {
            "Initial_Cash": init_eq,
            "Final_Equity": final_eq,
            "Total_Return": total_return,
            "Benchmark_Return": benchmark_return,
            "Annual_Return": annual_return,
            "Max_Drawdown": max_drawdown,
            "Sharpe_Ratio": sharpe,
            "Calmar_Ratio": calmar,
            "Total_Trades_Pairs": total_closed_trades,
            "Win_Rate": win_rate,
            "Tear_Sheet_Yearly": pd.DataFrame(tear_sheet_yearly) if tear_sheet_yearly else pd.DataFrame(),
            "Tear_Sheet_Monthly": pd.DataFrame(tear_sheet_monthly) if tear_sheet_monthly else pd.DataFrame()
        }
        return report

# --- 测试入口 ---
if __name__ == "__main__":
    test_file = "backtest_data/final_vault/600519.parquet"
    if os.path.exists(test_file):
        print(f"正在对 {test_file} 进行策略回测测试...")
        # 策略定义：收盘价站上 20 日线，且 MACD 柱子翻红 (买入)；跌破 10 日线止损或风控止损 (卖出)。
        buy_cond = "Close_Qfq > MA_20 and MACD_Hist > 0"
        sell_cond = "Close_Qfq < MA_10"
        
        runner = StrategyRunner(
            data_path=test_file,
            buy_logic=buy_cond,
            sell_logic=sell_cond,
            stop_loss_pct=0.08, # 8% 固定止损
            max_hold_days=20    # 持股不超过 20 天
        )
        
        # 运行回测大循环
        curve_df, trade_logs = runner.run()
        
        # 打印战报
        report = runner.generate_report(curve_df)
        print("\n🏆 === 终极战报 ===")
        for k, v in report.items():
            if "Return" in k or "Drawdown" in k or "Rate" in k:
                print(f"  {k}: {v:.2%}")
            else:
                print(f"  {k}: {v}")
                
        print(f"\n查看最后 3 笔交易流水:")
        for t in trade_logs[-3:]:
            print(f"  [{t['Date'].date()}] {t['Type']} {t['Shares']}股 @ {t['Price']:.2f}")
    else:
        print("未找到测试数据，请先运行数据引擎脚本！")
