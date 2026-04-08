from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
import csv
import io
import os


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MARKET_TYPE_MAP = {
    'FO':  'options',
    'EQ':  'indian_stocks',
    'CDS': 'forex',
    'COM': 'indian_stocks',
    'MF':  'indian_stocks',
}

EXEC_TIME_FORMATS = (
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%d %H:%M:%S',
)

TRADE_DATE_FORMATS = (
    '%m/%d/%Y',   # 04/04/2022
    '%#m/%#d/%Y', # 4/4/2022  (Windows)
    '%-m/%-d/%Y', # 4/4/2022  (Linux/Mac)
    '%Y-%m-%d',   # ISO fallback
)


def _parse_trade_date(raw: str) -> str:
    """
    Normalize trade_date to YYYY-MM-DD regardless of input format.
    Zerodha exports dates like '4/4/2022' — converts to '2022-04-04'.
    """
    raw = raw.strip()
    for fmt in TRADE_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return raw  # return as-is if nothing matches


def _parse_exec_time(raw: str):
    """Parse execution time string into datetime."""
    raw = raw.strip()
    for fmt in EXEC_TIME_FORMATS:
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


def _vwap(legs: list):
    """Compute VWAP price and total quantity from execution legs."""
    total_qty = sum(l['qty'] for l in legs)
    if total_qty == 0:
        return Decimal('0'), Decimal('0')
    total_value = sum(l['qty'] * l['price'] for l in legs)
    price = (total_value / total_qty).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return price, total_qty


def _earliest_time_str(legs: list, fmt='%H:%M') -> str:
    """Return earliest execution time among legs as formatted string."""
    times = [l['time'] for l in legs if l.get('time') is not None]
    return min(times).strftime(fmt) if times else ''


def _make_group():
    return {'buys': [], 'sells': [], 'segment': '', 'exchange': ''}


# ---------------------------------------------------------------------------
# Core normalizer — accepts any iterable of dicts
# ---------------------------------------------------------------------------

def normalize_zerodha(raw_rows):
    """
    Normalize Zerodha tradebook rows.

    Accepts an iterable of dicts (e.g. from csv.DictReader).
    Groups by (symbol, trade_date), computes VWAP entry/exit prices.

    IMPORTANT: Zerodha exports TSV (tab-separated), not CSV.
    If passing rows from csv.DictReader, open with delimiter='\\t'.
    Or use normalize_zerodha_from_file() / normalize_zerodha_from_string()
    which handle this automatically.
    """
    groups = defaultdict(_make_group)

    for row in raw_rows:
        try:
            symbol         = (row.get('symbol') or '').strip()
            trade_date_raw = (row.get('trade_date') or '').strip()
            trade_type     = (row.get('trade_type') or '').strip().lower()

            if not symbol or not trade_date_raw:
                continue

            trade_date_normalized = _parse_trade_date(trade_date_raw)
            qty   = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))

        except Exception:
            continue

        key   = (symbol, trade_date_normalized)
        group = groups[key]
        group['segment']  = row.get('segment', '').strip().upper()
        group['exchange'] = row.get('exchange', 'NSE').strip().upper()

        exec_time = _parse_exec_time(row.get('order_execution_time') or '')
        leg = {'qty': qty, 'price': price, 'time': exec_time}

        if trade_type == 'buy':
            group['buys'].append(leg)
        elif trade_type == 'sell':
            group['sells'].append(leg)

    return _build_normalized(groups)


# ---------------------------------------------------------------------------
# File-based entry point — handles TSV/CSV automatically
# ---------------------------------------------------------------------------

def normalize_zerodha_from_file(filepath: str, chunk_size: int = 10_000):
    """
    Read a Zerodha tradebook file and return normalized trades.

    Auto-detects tab vs comma delimiter by sniffing the first line.
    Streams in chunks so large files don't exhaust memory.
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    with open(filepath, newline='', encoding='utf-8-sig') as fh:
        first_line = fh.readline()
        delimiter  = '\t' if '\t' in first_line else ','
        fh.seek(0)

        reader = csv.DictReader(fh, delimiter=delimiter)
        groups = defaultdict(_make_group)
        chunk  = []

        for i, row in enumerate(reader, 1):
            chunk.append(row)
            if i % chunk_size == 0:
                _accumulate_groups(chunk, groups)
                chunk.clear()

        if chunk:
            _accumulate_groups(chunk, groups)

    return _build_normalized(groups)


def normalize_zerodha_from_string(content: str):
    """
    Normalize from raw file content string (e.g. uploaded file read into memory).
    Auto-detects tab vs comma delimiter.
    """
    first_line = content.split('\n')[0]
    delimiter  = '\t' if '\t' in first_line else ','
    reader     = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    return normalize_zerodha(reader)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _accumulate_groups(rows, groups):
    for row in rows:
        try:
            symbol         = (row.get('symbol') or '').strip()
            trade_date_raw = (row.get('trade_date') or '').strip()
            trade_type     = (row.get('trade_type') or '').strip().lower()

            if not symbol or not trade_date_raw:
                continue

            trade_date_normalized = _parse_trade_date(trade_date_raw)
            qty   = Decimal(str(row.get('quantity') or 0))
            price = Decimal(str(row.get('price') or 0))

        except Exception:
            continue

        key   = (symbol, trade_date_normalized)
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
    normalized = []

    for (symbol, trade_date), data in groups.items():
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
            'trade_date':  trade_date,
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