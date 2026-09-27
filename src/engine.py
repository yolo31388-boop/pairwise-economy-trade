"""经济交易系统"""
import copy
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
MIN_PRICE = Decimal("0.01")
MAX_PRICE = Decimal("1000000")


class TradeError(Exception):
    pass


class InvalidPriceError(TradeError):
    pass


class InsufficientFundsError(TradeError):
    pass


class InsufficientSpaceError(TradeError):
    pass


class InsufficientItemError(TradeError):
    pass


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
    capacity: int = 20
    frozen: float = 0.0


def _to_cents(value) -> Decimal:
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


class TradeSystem:
    def __init__(self):
        self.players: dict[str, Player] = {}
        self.tax_rate = Decimal("0.05")
        self.tax_collected = Decimal("0.00")
        self.ledger: list[dict] = []
        self.active_trades: dict[tuple, dict] = {}
        self.auctions: dict[str, dict] = {}

    # ---- bug2: 价格上下限校验 ----
    def _validate_price(self, price):
        price = _to_cents(price)
        if price < MIN_PRICE or price > MAX_PRICE:
            raise InvalidPriceError(f"价格 {price} 超出范围 [{MIN_PRICE}, {MAX_PRICE}]")
        return price

    # ---- bug7: 遍历所有格子统计/扣减堆叠 ----
    def _count_item(self, player, item_id):
        return sum(i.quantity for i in player.inventory if i.id == item_id)

    def _remove_item(self, player, item_id, quantity):
        remaining = quantity
        kept = []
        for item in player.inventory:
            if item.id == item_id and remaining > 0:
                take = min(item.quantity, remaining)
                item.quantity -= take
                remaining -= take
            if item.quantity > 0:
                kept.append(item)
        player.inventory = kept
        if remaining > 0:
            raise InsufficientItemError(f"物品 {item_id} 数量不足")

    def _free_slots(self, player, item_id):
        if any(i.id == item_id for i in player.inventory):
            return True  # 可堆叠进已有格子
        return len(player.inventory) < player.capacity

    def _add_item(self, player, item_id, name, quantity):
        for item in player.inventory:
            if item.id == item_id:
                item.quantity += quantity
                return
        player.inventory.append(Item(item_id, name, quantity))

    # ---- bug5: 定点数税率，四舍五入到最小单位 ----
    def calculate_tax(self, amount):
        return float(_to_cents(_to_cents(amount) * self.tax_rate))

    # ---- bug1: 事务语义，全成功或全回滚 ----
    def trade(self, buyer_id, seller_id, item_id, price, quantity=1):
        buyer = self.players[buyer_id]
        seller = self.players[seller_id]
        unit_price = self._validate_price(price)
        if not isinstance(quantity, int) or quantity <= 0:
            raise TradeError("数量必须为正整数")
        total = _to_cents(unit_price * quantity)
        tax = _to_cents(total * self.tax_rate)

        # 交易前校验：余额、物品总量、背包空间（bug3）
        if _to_cents(buyer.gold) < total:
            raise InsufficientFundsError("买家余额不足")
        if self._count_item(seller, item_id) < quantity:
            raise InsufficientItemError("卖家物品不足")
        if not self._free_slots(buyer, item_id):
            raise InsufficientSpaceError("买家背包空间不足")

        snapshot = (copy.deepcopy(buyer), copy.deepcopy(seller),
                    self.tax_collected, len(self.ledger))
        try:
            buyer.gold = float(_to_cents(buyer.gold) - total)
            seller.gold = float(_to_cents(seller.gold) + (total - tax))
            self.tax_collected += tax
            self.ledger.append({
                "buyer": buyer_id, "seller": seller_id, "item": item_id,
                "quantity": quantity, "total": str(total), "tax": str(tax),
            })
            self._remove_item(seller, item_id, quantity)
            self._add_item(buyer, item_id, item_id, quantity)
        except Exception:
            self.players[buyer_id], self.players[seller_id] = snapshot[0], snapshot[1]
            self.tax_collected = snapshot[2]
            del self.ledger[snapshot[3]:]
            raise
        return True

    # ---- bug4: 竞价冻结资金，被超价后解冻 ----
    def auction_bid(self, bidder_id, auction_id, amount):
        bidder = self.players[bidder_id]
        amount = _to_cents(amount)
        if amount <= 0:
            raise InvalidPriceError("出价必须为正")
        available = _to_cents(bidder.gold) - _to_cents(bidder.frozen)
        if available < amount:
            raise InsufficientFundsError("可用余额不足，无法冻结出价")

        auction = self.auctions.get(auction_id)
        if auction and amount <= _to_cents(auction["amount"]):
            raise TradeError("出价必须高于当前最高价")
        if auction:  # 解冻前出价者
            prev = self.players[auction["bidder"]]
            prev.frozen = float(_to_cents(prev.frozen) - _to_cents(auction["amount"]))

        bidder.frozen = float(_to_cents(bidder.frozen) + amount)
        self.auctions[auction_id] = {"bidder": bidder_id, "amount": str(amount)}
        return True

    # ---- bug6: 交易确认超时，超时自动取消并归还物品 ----
    def create_trade(self, p1, p2, item_id=None, quantity=1, timeout=30.0):
        key = (p1, p2)
        if key in self.active_trades:
            raise TradeError("交易已存在")
        reserved = None
        if item_id is not None:
            owner = self.players[p1]
            if self._count_item(owner, item_id) < quantity:
                raise InsufficientItemError("物品不足，无法发起交易")
            reserved = Item(item_id, item_id, quantity)
            self._remove_item(owner, item_id, quantity)
        self.active_trades[key] = {
            "state": "pending",
            "reserved": reserved,
            "deadline": time.monotonic() + timeout,
        }

    def confirm_trade(self, p1, p2):
        key = (p1, p2)
        self._expire(key)
        record = self.active_trades.pop(key)
        reserved = record["reserved"]
        if reserved is not None:
            receiver = self.players[p2]
            if not self._free_slots(receiver, reserved.id):
                self._add_item(self.players[p1], reserved.id, reserved.name, reserved.quantity)
                raise InsufficientSpaceError("对方背包空间不足，物品已退回")
            self._add_item(receiver, reserved.id, reserved.name, reserved.quantity)
        return True

    def _expire(self, key):
        record = self.active_trades.get(key)
        if record and time.monotonic() >= record["deadline"]:
            self._cancel(key)
            raise TradeError("交易已超时自动取消")

    def _cancel(self, key):
        record = self.active_trades.pop(key)
        reserved = record["reserved"]
        if reserved is not None:
            self._add_item(self.players[key[0]], reserved.id, reserved.name, reserved.quantity)

    def check_timeouts(self):
        expired = [k for k, v in self.active_trades.items()
                   if time.monotonic() >= v["deadline"]]
        for key in expired:
            self._cancel(key)
        return expired

    # ---- bug7: 堆叠拆分遍历所有格子 ----
    def split_stack(self, player_id, item_id, quantity):
        p = self.players[player_id]
        if quantity <= 0 or self._count_item(p, item_id) < quantity:
            return None
        name = next(i.name for i in p.inventory if i.id == item_id)
        self._remove_item(p, item_id, quantity)
        return Item(item_id, name, quantity)
