import uuid
from sortedcontainers import SortedList
from typing import List, Tuple, Dict

class OrderBook:
    def __init__(self):
        self.bids = SortedList()  # (-price, timestamp, order_id, original_price, quantity, user)
        self.asks = SortedList()  # (price, timestamp, order_id, price, quantity, user)
        self.orders: Dict[str, tuple] = {}
        self.timestamp = 0

    def add_limit_order(self, side: str, price: int, quantity: int, user: str) -> Tuple[str, List[Tuple]]:
        if price <= 0 or quantity <= 0:
            raise ValueError("Invalid order parameters")
        
        order_id = str(uuid.uuid4())
        self.timestamp += 1

        # Check for immediate matches
        matches, remaining_quantity = self._check_immediate_matches(side, price, quantity)

        # If there's any unmatched quantity, add it to the book
        if remaining_quantity > 0:
            entry = (
                -price if side == "buy" else price,
                self.timestamp,
                order_id,
                price,
                remaining_quantity,
                user
            )
            if side == "buy":
                self.bids.add(entry)
            else:
                self.asks.add(entry)

            self.orders[order_id] = (side, price, remaining_quantity, user)

        return order_id, matches

    def _check_immediate_matches(self, side: str, price: int, quantity: int) -> Tuple[List[Tuple], int]:
        matches = []
        remaining = quantity
        opposite = self.asks if side == "buy" else self.bids

        while remaining > 0 and opposite:
            best = opposite[0]
            best_price = best[3]

            # Ensure orders only match when valid
            if (side == "buy" and best_price > price) or (side == "sell" and best_price < price):
                break  # No match possible
            
            fill_qty = min(remaining, best[4])
            matches.append((best_price, fill_qty, best[5]))
            remaining -= fill_qty

            # Update or remove matched order
            if best[4] > fill_qty:
                new_quantity = best[4] - fill_qty
                new_entry = (*best[:4], new_quantity, best[5])
                opposite.discard(best)
                opposite.add(new_entry)
                self.orders[best[2]] = ('sell' if opposite is self.asks else 'buy', best[3], new_quantity, best[5])
            else:
                opposite.discard(best)
                del self.orders[best[2]]

        return matches, remaining

    def cancel_limit_order(self, user: str, price: int, quantity: int, side: str) -> bool:
        target_orders = self.bids if side == "buy" else self.asks
        for order_id, (s, p, q, u) in list(self.orders.items()):
            if u == user and s == side and p == price and q == quantity:
                # Find and remove the exact entry from bids/asks
                for entry in target_orders:
                    if entry[2] == order_id:  # Match order_id
                        target_orders.discard(entry)
                        del self.orders[order_id]
                        return True
        return False

    def match_market_order(self, side: str, quantity: int) -> List[Tuple]:
        matches = []
        remaining = quantity
        opposite = self.bids if side == "sell" else self.asks
        
        while remaining > 0 and opposite:
            best = opposite[0]
            fill_qty = min(remaining, best[4])
            matches.append((best[3], fill_qty, best[5]))
            remaining -= fill_qty
            
            if best[4] > fill_qty:
                new_entry = (*best[:4], best[4] - fill_qty, best[5])
                opposite.discard(best)
                opposite.add(new_entry)
            else:
                opposite.discard(best)
                del self.orders[best[2]]
        
        return matches

    def get_market_data(self) -> dict:
        return {
            "bids": [{"price": entry[3], "quantity": entry[4]} for entry in self.bids],
            "asks": [{"price": entry[3], "quantity": entry[4]} for entry in self.asks]
        }