from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def normalize_zerodha(raw_rows):
    """
    Zerodha tradebook CSV — one row per execution leg.
    Groups by (symbol, trade_date), computes VWAP entry/exit prices.
    """
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        symbol = (row.get('symbol') or '').strip()
        trade_date_raw = (row.get('trade_date') or '').strip()
        trade_type = (row.get('trade_type') or '').strip().lower()

        if not symbol or not trade_date_raw:
            continue

        try:
            qty = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))
        except Exception:
            continue

        key = (symbol, trade_date_raw)
        groups[key]['segment'] = row.get('segment', '').strip().upper()
        groups[key]['exchange'] = row.get('exchange', 'NSE').strip().upper()

        exec_time_raw = (row.get('order_execution_time') or '').strip()
        exec_time = None
        if exec_time_raw:
            for fmt in ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
                try:
                    exec_time = datetime.strptime(exec_time_raw, fmt)
                    break
                except ValueError:
                    continue

        entry = {'qty': qty, 'price': price, 'time': exec_time}

        if trade_type == 'buy':
            groups[key]['buys'].append(entry)
        elif trade_type == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for (symbol, trade_date_raw), data in groups.items():
        buys = data['buys']
        sells = data['sells']
        segment = data['segment']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        def vwap(legs):
            total_qty = sum(l['qty'] for l in legs)
            if total_qty == 0:
                return Decimal('0'), Decimal('0')
            total_value = sum(l['qty'] * l['price'] for l in legs)
            return (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), total_qty

        buy_vwap, total_buy_qty = vwap(buys)
        sell_vwap, total_sell_qty = vwap(sells)

        direction = 'long' if total_buy_qty >= total_sell_qty else 'short'

        if direction == 'long':
            entry_price = buy_vwap
            exit_price = sell_vwap if sells else None
            quantity = total_buy_qty
        else:
            entry_price = sell_vwap
            exit_price = buy_vwap if buys else None
            quantity = total_sell_qty

        all_legs = buys + sells
        all_times = [l['time'] for l in all_legs if l['time'] is not None]
        trade_time_str = min(all_times).strftime('%H:%M') if all_times else ''

        market_type_map = {
            'FO':  'options',
            'EQ':  'indian_stocks',
            'CDS': 'forex',
            'COM': 'indian_stocks',
            'MF':  'indian_stocks',
            
        }
        market_type = market_type_map.get(segment, 'indian_stocks')

        normalized.append({
            'symbol': symbol,
            'trade_date': trade_date_raw,
            'time': trade_time_str,
            'direction': direction,
            'quantity': str(quantity),
            'entry_price': str(entry_price),
            'exit_price': str(exit_price) if exit_price is not None else '',
            'fees': '0',
            'market_type': market_type,
            'exchange': exchange,
            'segment': segment,
        })

    return normalized