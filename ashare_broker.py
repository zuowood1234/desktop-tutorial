import math
import pandas as pd
import numpy as np

class AShareBroker:
    """
    符合 A 股实战规则的底层交易回测引擎
    特点：
    1. 强制 100 股向下取整
    2. 绝对 T+1 限制，今日买入的持仓明日才可用
    3. 支持佣金与印花税双重扣除
    4. 完美识别涨跌停板熔断机制，并在无法买卖时宣告指令失败
    """
    def __init__(self, initial_cash=200000.0, commission=0.00025, stamp_duty=0.0005, slippage=0.001):
        self.initial_cash = initial_cash
        self.cash = initial_cash
        
        # 仓位管理：必须分离 "总持股数" 和 "可用持股数" (由于T+1机制)
        # 今天的可用持股 = 昨天的总持股；卖出时只能从 "可用持股" 中扣减
        self.total_shares = 0       # 总持有股数
        self.available_shares = 0   # 当前可以卖出的可用股数（T+1解锁）
        
        self.commission_rate = commission
        self.stamp_duty_rate = stamp_duty
        self.slippage = slippage    # 以百分比表示的隐形成本，默认千分之一
        
        # 交易记录流水
        self.trades = []
        
        # 状态追踪
        self.current_idx = 0        # 整个回测时间线的进度游标
        self.current_date = None
        self.last_close = None      # 记录上一日收盘价用于计算滑点/涨跌停备用

    def _calc_commission(self, trade_amount):
        """A 股佣金计算，实盘一般有最低 5 元的限制"""
        fee = trade_amount * self.commission_rate
        return max(fee, 5.0)

    def _get_lots_to_buy(self, cash_available, price):
        """计算能买多少股，强制要求为 100 股的整数倍"""
        max_shares = cash_available / price
        lots = math.floor(max_shares / 100)
        return lots * 100

    def daily_update_t1_lock(self):
        """
        跨日更新。进入新的一天时，将昨天刚买被锁定的股份释放为“可用份额”。
        在每日行情循环的最开始调用！
        """
        self.available_shares = self.total_shares

    def evaluate_portfolio(self, current_price):
        """评估当前账户总净值 (现金 + 股票现值)"""
        # 如果当前股票停牌 (price 为 Nan)，依然需要计算总资产，外部应当传入前一天的有效收盘价
        if pd.isna(current_price):
            current_price = self.last_close if self.last_close is not None else 0
            
        stock_value = self.total_shares * current_price
        return self.cash + stock_value

    def record_last_price(self, price):
        """更新最后一次有效价格，用于停牌日净值计算"""
        if not pd.isna(price):
            self.last_close = price

    def submit_buy_order(self, date, trigger_price, limit_up_price, current_high, is_open_auction=False):
        """
        提交全仓买入指令 (All-in 模型)。
        参数:
        trigger_price - 实际触发买单的价格 (若是尾盘买入则为收盘价，次日开盘买则为次日开盘价)
        limit_up_price - 当日涨停价
        current_high - 当日最高价 (若一字板，最高价必定=涨停价)
        is_open_auction - 是否是集合竞价开盘买
        """
        if self.cash <= 0:
            return False, "现金不足"

        # 1. 检查熔断机制 (涨停买不进)
        if is_open_auction:
            # 开盘买入：如果开盘价一字涨停，无法买入
            if trigger_price >= limit_up_price * 0.999: # 考虑0.1分的浮点误差
                return False, f"开盘一字涨停，无法买入 ({trigger_price} 触及涨停 {limit_up_price})"
        else:
            # 尾盘买入：如果全天封死涨停，或者尾盘刚好卡在涨停，普通单排不进去
            if trigger_price >= limit_up_price * 0.999 or current_high >= limit_up_price * 0.999:
                 return False, f"遇涨停板筹码封锁，指令作废 ({current_high} 触及涨停 {limit_up_price})"

        # 2. 施加滑点 (抢筹成本增加)
        execution_price = trigger_price * (1 + self.slippage)

        # 3. 计算实际可买数量 (向下取整百股)
        shares_to_buy = self._get_lots_to_buy(self.cash, execution_price)
        if shares_to_buy < 100:
            return False, f"全部资金({self.cash:.2f})买不起1手股票(需{execution_price*100:.2f})"

        # 4. 执行扣款并锁定份额 (T日买入，此时份额进 total_shares, 不进 available)
        trade_amount = shares_to_buy * execution_price
        comm = self._calc_commission(trade_amount)
        stamp = trade_amount * self.stamp_duty_rate
        total_cost = trade_amount + comm + stamp

        if self.cash < total_cost: 
            # 理论上不会发生，但在极边缘情况下加上印花税后金额超限，稍微再减一手重试
            shares_to_buy -= 100
            if shares_to_buy < 100: return False, "加上手续费与印花税后不足以买1手"
            trade_amount = shares_to_buy * execution_price
            comm = self._calc_commission(trade_amount)
            stamp = trade_amount * self.stamp_duty_rate
            total_cost = trade_amount + comm + stamp

        # 正式成交
        self.cash -= total_cost
        self.total_shares += shares_to_buy
        # 注意: available_shares 此时不增加，等到明天 daily_update 时解锁

        trade_record = {
            "Date": date,
            "Type": "BUY",
            "Price": execution_price, # 已含滑点
            "Shares": shares_to_buy,
            "Amount": trade_amount,
            "Commission": comm,
            "Stamp_Duty": stamp,
            "Cash_Left": self.cash
        }
        self.trades.append(trade_record)
        return True, f"成功买入 {shares_to_buy} 股，成交价 {execution_price:.2f}"

    def submit_sell_order(self, date, trigger_price, limit_down_price, current_low, is_open_auction=False):
        """
        提交全仓卖出指令。
        """
        if self.available_shares <= 0:
            if self.total_shares > 0:
                return False, "持仓处于 T+1 锁定期，今日不可卖出！"
            return False, "没有可用持仓"

        # 1. 检查熔断机制 (跌停卖不出)
        if is_open_auction:
             if trigger_price <= limit_down_price * 1.001:
                 return False, f"开盘一字跌停，无法逃离 ({trigger_price} 触及跌停 {limit_down_price})"
        else:
             # 如果最低价摸到了跌停板并且收盘价也在跌停板附近，或者触发止损价但被跌停板压制
             if trigger_price <= limit_down_price * 1.001 or current_low <= limit_down_price * 1.001:
                 return False, f"遇跌停板封锁，卖单无法撮合 ({current_low} 触及跌停 {limit_down_price})"

        # 2. 施加滑点 (砸盘滑价，卖得更贱)
        execution_price = trigger_price * (1 - self.slippage)

        # 3. 清仓抛售所有可用持仓
        shares_to_sell = self.available_shares
        trade_amount = shares_to_sell * execution_price

        # 4. 算账 (佣金 + 印花税)
        comm = self._calc_commission(trade_amount)
        stamp = trade_amount * self.stamp_duty_rate
        net_proceeds = trade_amount - comm - stamp

        # 正式成交
        self.cash += net_proceeds
        self.total_shares -= shares_to_sell
        self.available_shares -= shares_to_sell

        trade_record = {
            "Date": date,
            "Type": "SELL",
            "Price": execution_price,
            "Shares": shares_to_sell,
            "Amount": trade_amount,
            "Commission": comm,
            "Stamp_Duty": stamp,
            "Cash_Left": self.cash
        }
        self.trades.append(trade_record)
        return True, f"成功卖出 {shares_to_sell} 股，成交价 {execution_price:.2f}"
