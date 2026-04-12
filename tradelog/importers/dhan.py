from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP


def normalize_dhan(raw_rows):
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        date_raw = row.get('date', '').strip()
        name = row.get('name', '').strip()
        side = row.get('buy/sell', '').strip().lower()
        status = row.get('status', '').strip().lower()

        if not name or not date_raw:
            continue

        # Only process traded rows
        if status != 'traded':
            continue

        price_str = row.get('trade_price', '0').replace('₹', '').replace(',', '').strip()
        qty_str = row.get('quantity/lot', '0').replace(',', '').strip()

        try:
            price = Decimal(price_str)
            qty = Decimal(qty_str)
        except Exception:
            continue

        exchange = row.get('exchange', 'NSE').strip().upper()
        segment_raw = row.get('segment', '').strip().lower()

        # Map Dhan segment to internal segment codes
        if 'derivative' in segment_raw or 'futures' in segment_raw or 'options' in segment_raw:
            segment = 'FO'
        elif 'equity' in segment_raw or 'cash' in segment_raw:
            segment = 'EQ'
        elif 'currency' in segment_raw:
            segment = 'CDS'
        elif 'commodity' in segment_raw:
            segment = 'COM'
        else:
            segment = 'EQ'

        # Parse date — Dhan uses M/D/YYYY format
        try:
            trade_date_iso = datetime.strptime(date_raw, '%m/%d/%Y').strftime('%Y-%m-%d')
        except ValueError:
            try:
                trade_date_iso = datetime.strptime(date_raw, '%d-%m-%Y').strftime('%Y-%m-%d')
            except ValueError:
                trade_date_iso = date_raw

        key = (name, trade_date_iso)
        groups[key]['segment'] = segment
        groups[key]['exchange'] = exchange

        time_raw = row.get('time', '').strip()
        exec_time = None
        if time_raw:
            try:
                exec_time = datetime.strptime(f"{date_raw} {time_raw}", '%m/%d/%Y %H:%M:%S')
            except ValueError:
                try:
                    exec_time = datetime.strptime(f"{date_raw} {time_raw}", '%m/%d/%Y %H:%M')
                except ValueError:
                    pass

        entry = {
            'qty':      qty,
            'price':    price,
            'time':     exec_time,
            'time_str': time_raw,
        }

        if side == 'buy':
            groups[key]['buys'].append(entry)
        elif side == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for (symbol, trade_date_iso), data in groups.items():
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
            exit_price  = sell_vwap if sells else None
            quantity    = total_buy_qty
            entry_legs  = buys
            exit_legs   = sells
        else:
            entry_price = sell_vwap
            exit_price  = buy_vwap if buys else None
            quantity    = total_sell_qty
            entry_legs  = sells
            exit_legs   = buys

        def earliest_time_str(legs, fmt='%H:%M:%S'):
            legs_with_dt = [l for l in legs if l.get('time') is not None]
            if legs_with_dt:
                return min(legs_with_dt, key=lambda l: l['time'])['time'].strftime(fmt)
            legs_with_str = [l for l in legs if l.get('time_str')]
            return legs_with_str[0]['time_str'] if legs_with_str else ''

        all_legs = buys + sells
        trade_time_str = earliest_time_str(all_legs)
        entry_time_str = earliest_time_str(entry_legs)
        exit_time_str  = earliest_time_str(exit_legs)

        market_type_map = {
            'FO':  'options',
            'EQ':  'indian_market',
            'CDS': 'forex',
            'COM': 'indian_market',
        }
        market_type = market_type_map.get(segment, 'indian_market')

        normalized.append({
            'symbol':      symbol,
            'trade_date':  trade_date_iso,
            'time':        trade_time_str,
            'entry_time':  entry_time_str,
            'exit_time':   exit_time_str,
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