"""经济交易 - 带7个bug"""
from dataclasses import dataclass, field

@dataclass
class Item:
    id: str
    name: str
    quantity: int

@dataclass
class Player:
    pid: str
    gold: float
    inventory: list[Item] = field(default_factory=list)

class TradeSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.tax_rate = 0.05
        self.active_trades = {}  # bug6: 无超时

    def trade(self, buyer_id, seller_id, item_id, price, quantity=1):
        buyer = self.players[buyer_id]
        seller = self.players[seller_id]
        # bug1: 无原子性
        buyer.gold -= price * quantity
        # bug2: 不校验价格正负
        # bug3: 不检查背包空间
        seller.inventory = [i for i in seller.inventory if i.id != item_id or i.quantity < quantity]
        buyer.inventory.append(Item(item_id, item_id, quantity))
        return True

    def auction_bid(self, bidder_id, auction_id, amount):
        bidder = self.players[bidder_id]
        # bug4: 不冻结资金
        return True

    def calculate_tax(self, amount):
        # bug5: 浮点无四舍五入
        return amount * self.tax_rate

    def create_trade(self, p1, p2):
        # bug6: 无超时
        self.active_trades[(p1, p2)] = "pending"

    def split_stack(self, player_id, item_id, quantity):
        # bug7: 只检查第一格
        p = self.players[player_id]
        for item in p.inventory:
            if item.id == item_id and item.quantity >= quantity:
                item.quantity -= quantity
                return Item(item_id, item.name, quantity)
        return None
