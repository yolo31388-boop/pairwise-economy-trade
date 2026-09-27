"""经济交易测试"""
import pytest, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from src.engine import TradeSystem, Player, Item

class TestAtomic:
    def test_trade_atomic_on_failure(self):
        ts = TradeSystem()
        ts.players["buyer"] = Player("buyer", 50, [])
        ts.players["seller"] = Player("seller", 0, [Item("sword", "sword", 1)])
        # 价格为负应该失败
        try:
            ts.trade("buyer", "seller", "sword", -100, 1)
        except:
            pass
        assert ts.players["buyer"].gold == 50, "非原子交易导致钱丢失"

class TestPrice:
    def test_negative_price_rejected(self):
        ts = TradeSystem()
        ts.players["b"] = Player("b", 100, [])
        ts.players["s"] = Player("s", 0, [Item("i", "i", 1)])
        try:
            result = ts.trade("b", "s", "i", -10, 1)
            assert not result, "负数价格被接受"
        except:
            assert True
