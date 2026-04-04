from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def normalize_fyers(raw_rows):
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        symbol      = row.get('symbol', '').strip()
        side        = row.get('side', '').strip().lower()      # BUY / SELL
        datetime_raw = row.get('date_&_time', '').strip()

        if not symbol or not datetime_raw or not side:
            continue

        price_str = row.get('traded_price', '0').replace(',', '').strip()
        qty_str   = row.get('qty', '0').replace(',', '').strip()

        try:
            price = Decimal(price_str) if price_str else Decimal('0')
            qty   = Decimal(qty_str)   if qty_str   else Decimal('0')
        except Exception:
            continue

        if qty == 0 or price == 0:
            continue

        # Parse "01 Apr 2026, 09:46:30 AM"
        dt = None
        for fmt in ('%d %b %Y, %I:%M:%S %p', '%d %b %Y, %I:%M %p'):
            try:
                dt = datetime.strptime(datetime_raw, fmt)
                break
            except ValueError:
                continue

        if dt is None:
            continue

        trade_date_iso = dt.strftime('%Y-%m-%d')
        trade_time_str = dt.strftime('%H:%M:%S')

        segment_raw = row.get('segment', '').strip().lower()
        if 'derivative' in segment_raw or 'futures' in segment_raw or 'options' in segment_raw:
            segment = 'FO'
        elif 'currency' in segment_raw or 'cds' in segment_raw:
            segment = 'CDS'
        elif 'commodity' in segment_raw or 'com' in segment_raw:
            segment = 'COM'
        else:
            segment = 'EQ'

        # Fyers doesn't have a separate exchange column — default NSE
        exchange = 'NSE'

        key = (symbol, trade_date_iso)
        groups[key]['segment']  = segment
        groups[key]['exchange'] = exchange

        entry = {
            'qty':      qty,
            'price':    price,
            'time':     dt,
            'time_str': trade_time_str,
        }

        if side == 'buy':
            groups[key]['buys'].append(entry)
        elif side == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for (symbol, trade_date_iso), data in groups.items():
        buys     = data['buys']
        sells    = data['sells']
        segment  = data['segment']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        def vwap(legs):
            total_qty = sum(l['qty'] for l in legs)
            if total_qty == 0:
                return Decimal('0'), Decimal('0')
            total_value = sum(l['qty'] * l['price'] for l in legs)
            return (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP), total_qty

        buy_vwap,  total_buy_qty  = vwap(buys)
        sell_vwap, total_sell_qty = vwap(sells)

        direction = 'long' if total_buy_qty >= total_sell_qty else 'short'

        if direction == 'long':
            entry_price = buy_vwap
            exit_price  = sell_vwap if sells else None
            quantity    = total_buy_qty
        else:
            entry_price = sell_vwap
            exit_price  = buy_vwap if buys else None
            quantity    = total_sell_qty

        all_legs = buys + sells
        legs_with_dt = [l for l in all_legs if l.get('time') is not None]
        if legs_with_dt:
            earliest = min(legs_with_dt, key=lambda l: l['time'])
            trade_time_str = earliest['time'].strftime('%H:%M:%S')
        else:
            trade_time_str = ''

        market_type_map = {
            'FO':  'options',
            'EQ':  'indian_stocks',
            'CDS': 'forex',
            'COM': 'indian_stocks',
        }
        market_type = market_type_map.get(segment, 'indian_stocks')

        normalized.append({
            'symbol':      symbol,
            'trade_date':  trade_date_iso,
            'time':        trade_time_str,
            'direction':   direction,
            'quantity':    str(quantity),
            'entry_price': str(entry_price),
            'exit_price':  str(exit_price) if exit_price is not None else '',
            'fees':        '0',
            'market_type': market_type,
            'exchange':    exchange,
            'segment':     segment,
        })

    return normalized