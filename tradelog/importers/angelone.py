from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def normalize_angelone(raw_rows):
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        # Angel One header "Scrip/Contract" normalizes to "scrip/contract"
        symbol = row.get('scrip/contract', '').strip()
        side = row.get('buy/sell', '').strip().lower()
        date_raw = row.get('date', '').strip()  # injected by parser from metadata

        if not symbol or not date_raw or not side:
            continue

        buy_price_str  = row.get('buy_price', '').replace('₹', '').replace(',', '').strip()
        sell_price_str = row.get('sell_price', '').replace('₹', '').replace(',', '').strip()
        qty_str        = row.get('quantity', '0').replace(',', '').strip()

        try:
            buy_price  = Decimal(buy_price_str)  if buy_price_str  else Decimal('0')
            sell_price = Decimal(sell_price_str) if sell_price_str else Decimal('0')
            qty        = Decimal(qty_str)        if qty_str        else Decimal('0')
        except Exception:
            continue

        # Skip fee-only rows (qty=0 AND both prices=0)
        if qty == 0 and buy_price == 0 and sell_price == 0:
            continue

        # Skip legs with no real price or no qty
        if side == 'buy'  and (buy_price  == 0 or qty == 0):
            continue
        if side == 'sell' and (sell_price == 0 or qty == 0):
            continue

        price = buy_price if side == 'buy' else sell_price

        exchange    = row.get('exchange', 'NSE').strip().upper()
        segment_raw = row.get('segment', '').strip().lower()

        if 'futures' in segment_raw or 'options' in segment_raw or 'fo' in segment_raw:
            segment = 'FO'
        elif 'currency' in segment_raw or 'cds' in segment_raw:
            segment = 'CDS'
        elif 'commodity' in segment_raw or 'com' in segment_raw:
            segment = 'COM'
        else:
            segment = 'EQ'

        # Parse date — injected as YYYY-MM-DD by parser, but handle raw formats too
        try:
            dt = datetime.strptime(date_raw, '%Y-%m-%d')
        except ValueError:
            try:
                dt = datetime.strptime(date_raw, '%m/%d/%Y %H:%M')
            except ValueError:
                try:
                    dt = datetime.strptime(date_raw, '%d-%m-%Y')
                except ValueError:
                    dt = None

        trade_date_iso = dt.strftime('%Y-%m-%d') if dt else date_raw
        trade_time_str = ''  # Angel One has no time column

        key = (symbol, trade_date_iso)
        groups[key]['segment'] = segment
        groups[key]['exchange'] = exchange

        entry = {
            'qty':      qty,
            'price':    price,
            'time_str': trade_time_str,
        }

        if side == 'buy':
            groups[key]['buys'].append(entry)
        elif side == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for (symbol, trade_date_iso), data in groups.items():
        buys    = data['buys']
        sells   = data['sells']
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
            'time':        '',
            'entry_time':  '',   
            'exit_time':   '',  
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