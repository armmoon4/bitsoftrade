from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def normalize_upstox(raw_rows):
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'segment': '', 'exchange': ''})

    for row in raw_rows:
        date_raw = row.get('date', '').strip()
        scrip_code = row.get('scrip_code', '').strip()
        side = row.get('side', '').strip().lower()

        if not scrip_code or not date_raw:
            continue

        price_str = row.get('price', '0').replace('₹', '').replace(',', '').strip()
        qty_str = row.get('quantity', '0').replace(',', '').strip()

        try:
            price = Decimal(price_str)
            qty = Decimal(qty_str)
        except Exception:
            continue

        segment = row.get('segment', '').strip().upper()
        exchange_raw = row.get('exchange', 'NSE').strip().upper()
        exchange = 'NSE' if exchange_raw == 'FON' else exchange_raw

        try:
            trade_date_iso = datetime.strptime(date_raw, '%d-%m-%Y').strftime('%Y-%m-%d')
        except ValueError:
            trade_date_iso = date_raw

        symbol = scrip_code
        if segment == 'FO':
            expiry = row.get('expiry', '').strip()
            strike = row.get('strike_price', '').strip()
            instr = row.get('instrument_type', '').strip().lower()
            opt_type = 'CE' if 'call' in instr else 'PE' if 'put' in instr else instr.upper()
            symbol = f"{scrip_code} {expiry} {strike} {opt_type}".strip()

        key = (symbol, trade_date_iso)
        groups[key]['segment'] = segment
        groups[key]['exchange'] = exchange

        time_raw = row.get('trade_time', '').strip()
        exec_time = None
        if time_raw:
            try:
                exec_time = datetime.strptime(f"{date_raw} {time_raw}", '%d-%m-%Y %H:%M:%S')
            except ValueError:
                try:
                    exec_time = datetime.strptime(f"{date_raw} {time_raw}", '%d-%m-%Y %H:%M')
                except ValueError:
                    pass

        entry = {
            'qty': qty,
            'price': price,
            'time': exec_time,
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
            exit_price = sell_vwap if sells else None
            quantity = total_buy_qty
        else:
            entry_price = sell_vwap
            exit_price = buy_vwap if buys else None
            quantity = total_sell_qty

        all_legs = buys + sells

        legs_with_dt = [l for l in all_legs if l['time'] is not None]
        if legs_with_dt:
            earliest = min(legs_with_dt, key=lambda l: l['time'])
            trade_time_str = earliest['time'].strftime('%H:%M:%S')
        else:
            legs_with_str = [l for l in all_legs if l.get('time_str')]
            trade_time_str = legs_with_str[0]['time_str'] if legs_with_str else ''

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
            'trade_date': trade_date_iso,
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