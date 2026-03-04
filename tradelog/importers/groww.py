from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

def normalize_groww(raw_rows):
    """
    Groww order history CSV/Excel — one row per executed order leg.
    """
    groups = defaultdict(lambda: {'buys': [], 'sells': [], 'exchange': ''})

    for row in raw_rows:
        order_status = row.get('order_status', '').strip().lower()
        if order_status and order_status != 'executed':
            continue

        symbol = row.get('symbol', '').strip()
        if not symbol:
            continue

        exec_datetime_raw = row.get('execution_date_and_time', '').strip()
        trade_date_raw = ''
        exec_time = None

        if exec_datetime_raw:
            for fmt in (
                '%d-%m-%Y %I:%M %p',
                '%d-%m-%Y %H:%M',
                '%Y-%m-%d %H:%M:%S',
                '%d/%m/%Y %I:%M %p',
                '%d/%m/%Y %H:%M',
            ):
                try:
                    exec_time = datetime.strptime(exec_datetime_raw, fmt)
                    trade_date_raw = exec_time.strftime('%Y-%m-%d')
                    break
                except ValueError:
                    continue

            if not trade_date_raw:
                date_token = exec_datetime_raw.split()[0] if exec_datetime_raw.split() else ''
                for dfmt in ('%d-%m-%Y', '%Y-%m-%d', '%d/%m/%Y'):
                    try:
                        exec_time = datetime.strptime(date_token, dfmt)
                        trade_date_raw = exec_time.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue

        if not trade_date_raw:
            continue

        trade_type = row.get('type', '').strip().lower()

        try:
            qty = Decimal(str(row.get('quantity') or 0))
            value = Decimal(str(row.get('value') or 0))
            price = (value / qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP) if qty > 0 else Decimal('0')
        except Exception:
            continue

        key = symbol
        groups[key]['exchange'] = row.get('exchange', 'NSE').strip().upper()

        entry = {'qty': qty, 'price': price, 'time': exec_time, 'date': trade_date_raw}

        if trade_type == 'buy':
            groups[key]['buys'].append(entry)
        elif trade_type == 'sell':
            groups[key]['sells'].append(entry)

    normalized = []

    for symbol, data in groups.items():
        buys = data['buys']
        sells = data['sells']
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
        all_dates = [l['date'] for l in all_legs if l.get('date')]
        trade_date_raw = min(all_dates) if all_dates else ''
        if not trade_date_raw:
            continue

        all_times = [l['time'] for l in all_legs if l.get('time') is not None]
        trade_time_str = min(all_times).strftime('%H:%M') if all_times else ''

        normalized.append({
            'symbol': symbol,
            'trade_date': trade_date_raw,
            'time': trade_time_str,
            'direction': direction,
            'quantity': str(quantity),
            'entry_price': str(entry_price),
            'exit_price': str(exit_price) if exit_price is not None else '',
            'fees': '0',
            'market_type': 'indian_stocks',
            'exchange': exchange,
            'segment': 'EQ',
        })

    return normalized