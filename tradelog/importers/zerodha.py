from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import csv
import os


# ---------------------------------------------------------------------------
# Helpers (defined once at module level, not re-created inside loops)
# ---------------------------------------------------------------------------

MARKET_TYPE_MAP = {
    'FO':  'options',
    'EQ':  'indian_stocks',
    'CDS': 'forex',
    'COM': 'indian_stocks',
    'MF':  'indian_stocks',
}

DATETIME_FORMATS = ('%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S')


def _parse_exec_time(raw: str):
    """Parse execution time string into datetime, trying multiple formats."""
    raw = raw.strip()
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _vwap(legs: list):
    """Compute VWAP price and total quantity from a list of execution legs."""
    total_qty = sum(l['qty'] for l in legs)
    if total_qty == 0:
        return Decimal('0'), Decimal('0')
    total_value = sum(l['qty'] * l['price'] for l in legs)
    price = (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return price, total_qty


def _earliest_time_str(legs: list, fmt='%H:%M') -> str:
    """Return the earliest execution time among legs, formatted as string."""
    times = [l['time'] for l in legs if l.get('time') is not None]
    return min(times).strftime(fmt) if times else ''


def _make_group():
    """Factory for a fresh group dict (avoids mutable defaultdict lambda issues)."""
    return {'buys': [], 'sells': [], 'segment': '', 'exchange': ''}


# ---------------------------------------------------------------------------
# Core normalizer — accepts an iterable of dicts (memory efficient)
# ---------------------------------------------------------------------------

def normalize_zerodha(raw_rows):
    """
    Normalize Zerodha tradebook rows (list or any iterable of dicts).

    Groups executions by (symbol, trade_date), computes VWAP entry/exit.

    Parameters
    ----------
    raw_rows : iterable of dict
        Each dict represents one execution leg from Zerodha's CSV.

    Returns
    -------
    list of dict  — one normalized trade record per (symbol, trade_date) group.
    """
    groups = defaultdict(_make_group)

    for row in raw_rows:
        try:
            symbol         = (row.get('symbol') or '').strip()
            trade_date_raw = (row.get('trade_date') or '').strip()
            trade_type     = (row.get('trade_type') or '').strip().lower()

            if not symbol or not trade_date_raw:
                continue

            qty   = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))

        except Exception:
            # Skip any malformed row silently; add logging here if needed
            continue

        key = (symbol, trade_date_raw)
        group = groups[key]
        group['segment']  = row.get('segment', '').strip().upper()
        group['exchange'] = row.get('exchange', 'NSE').strip().upper()

        exec_time = _parse_exec_time(row.get('order_execution_time') or '')
        leg = {'qty': qty, 'price': price, 'time': exec_time}

        if trade_type == 'buy':
            group['buys'].append(leg)
        elif trade_type == 'sell':
            group['sells'].append(leg)

    # ------------------------------------------------------------------
    # Build output records
    # ------------------------------------------------------------------
    normalized = []

    for (symbol, trade_date_raw), data in groups.items():
        buys    = data['buys']
        sells   = data['sells']
        segment = data['segment']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        buy_vwap,  total_buy_qty  = _vwap(buys)
        sell_vwap, total_sell_qty = _vwap(sells)

        if total_buy_qty >= total_sell_qty:
            direction   = 'long'
            entry_price = buy_vwap
            exit_price  = sell_vwap if sells else None
            quantity    = total_buy_qty
            entry_legs  = buys
            exit_legs   = sells
        else:
            direction   = 'short'
            entry_price = sell_vwap
            exit_price  = buy_vwap if buys else None
            quantity    = total_sell_qty
            entry_legs  = sells
            exit_legs   = buys

        all_legs = buys + sells

        normalized.append({
            'symbol':      symbol,
            'trade_date':  trade_date_raw,
            'time':        _earliest_time_str(all_legs),
            'entry_time':  _earliest_time_str(entry_legs),
            'exit_time':   _earliest_time_str(exit_legs),
            'direction':   direction,
            'quantity':    str(quantity),
            'entry_price': str(entry_price),
            'exit_price':  str(exit_price) if exit_price is not None else '',
            'fees':        '0',
            'market_type': MARKET_TYPE_MAP.get(segment, 'indian_stocks'),
            'exchange':    exchange,
            'segment':     segment,
        })

    return normalized


# ---------------------------------------------------------------------------
# Convenience: stream directly from a large CSV file in chunks
# ---------------------------------------------------------------------------

def normalize_zerodha_from_file(filepath: str, chunk_size: int = 10_000):
    """
    Memory-efficient entry point for large CSV files.

    Reads the CSV in chunks of `chunk_size` rows so the entire file
    is never loaded into memory at once.

    Parameters
    ----------
    filepath   : path to Zerodha tradebook CSV
    chunk_size : rows per chunk (tune based on available RAM)

    Returns
    -------
    list of normalized trade dicts
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV not found: {filepath}")

    # We still need to group across the full file, so we accumulate
    # groups incrementally rather than building a huge list first.
    groups = defaultdict(_make_group)

    with open(filepath, newline='', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        chunk  = []

        for i, row in enumerate(reader, 1):
            chunk.append(row)

            if i % chunk_size == 0:
                _accumulate_groups(chunk, groups)
                chunk.clear()          # free memory before next chunk

        if chunk:                      # process remaining rows
            _accumulate_groups(chunk, groups)

    return _build_normalized(groups)


def _accumulate_groups(rows, groups):
    """Add a batch of raw rows into the shared groups dict."""
    for row in rows:
        try:
            symbol         = (row.get('symbol') or '').strip()
            trade_date_raw = (row.get('trade_date') or '').strip()
            trade_type     = (row.get('trade_type') or '').strip().lower()

            if not symbol or not trade_date_raw:
                continue

            qty   = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))

        except Exception:
            continue

        key = (symbol, trade_date_raw)
        group = groups[key]
        group['segment']  = row.get('segment', '').strip().upper()
        group['exchange'] = row.get('exchange', 'NSE').strip().upper()

        exec_time = _parse_exec_time(row.get('order_execution_time') or '')
        leg = {'qty': qty, 'price': price, 'time': exec_time}

        if trade_type == 'buy':
            group['buys'].append(leg)
        elif trade_type == 'sell':
            group['sells'].append(leg)


def _build_normalized(groups):
    """Convert accumulated groups dict into final normalized list."""
    normalized = []

    for (symbol, trade_date_raw), data in groups.items():
        buys     = data['buys']
        sells    = data['sells']
        segment  = data['segment']
        exchange = data['exchange']

        if not buys and not sells:
            continue

        buy_vwap,  total_buy_qty  = _vwap(buys)
        sell_vwap, total_sell_qty = _vwap(sells)

        if total_buy_qty >= total_sell_qty:
            direction   = 'long'
            entry_price = buy_vwap
            exit_price  = sell_vwap if sells else None
            quantity    = total_buy_qty
            entry_legs  = buys
            exit_legs   = sells
        else:
            direction   = 'short'
            entry_price = sell_vwap
            exit_price  = buy_vwap if buys else None
            quantity    = total_sell_qty
            entry_legs  = sells
            exit_legs   = buys

        normalized.append({
            'symbol':      symbol,
            'trade_date':  trade_date_raw,
            'time':        _earliest_time_str(buys + sells),
            'entry_time':  _earliest_time_str(entry_legs),
            'exit_time':   _earliest_time_str(exit_legs),
            'direction':   direction,
            'quantity':    str(quantity),
            'entry_price': str(entry_price),
            'exit_price':  str(exit_price) if exit_price is not None else '',
            'fees':        '0',
            'market_type': MARKET_TYPE_MAP.get(segment, 'indian_stocks'),
            'exchange':    exchange,
            'segment':     segment,
        })

    return normalized