from django.db.models import Sum, Avg, Count, Max, Min, Q, F
from django.db.models.functions import TruncDate, ExtractHour
from decimal import Decimal
import math
from datetime import date, timedelta


def _fmt_date(d):
    """Format a date as 'Mon D' without zero-padding, cross-platform."""
    if hasattr(d, 'strftime'):
        return d.strftime('%b ') + str(d.day)
    return str(d)


def _consecutive_streaks(values):
    """Returns (max_winning_streak, max_losing_streak) from a list of daily P&Ls."""
    max_win = max_loss = cur_win = cur_loss = 0
    for v in values:
        if v > 0:
            cur_win += 1; cur_loss = 0
        elif v < 0:
            cur_loss += 1; cur_win = 0
        else:
            cur_win = cur_loss = 0
        max_win = max(max_win, cur_win)
        max_loss = max(max_loss, cur_loss)
    return max_win, max_loss


def get_performance_report_data(qs):
    total = qs.count()
    if total == 0:
        return {'message': 'No trades in the selected range.'}

    agg = qs.aggregate(
        net_pnl=Sum('total_pnl'),
        avg_trade_pnl=Avg('total_pnl'),
        largest_win=Max('total_pnl'),
        largest_loss=Min('total_pnl'),
        gross_profit=Sum('total_pnl', filter=Q(total_pnl__gt=0)),
        gross_loss=Sum('total_pnl', filter=Q(total_pnl__lt=0)),
        avg_win=Avg('total_pnl', filter=Q(total_pnl__gt=0)),
        avg_loss=Avg('total_pnl', filter=Q(total_pnl__lt=0)),
    )

    wins = qs.filter(total_pnl__gt=0).count()
    win_rate = round(wins / total * 100, 2) if total else 0

    gross_profit = agg['gross_profit'] or Decimal('0')
    gross_loss = abs(agg['gross_loss'] or Decimal('0'))
    profit_factor = round(float(gross_profit / gross_loss), 2) if gross_loss else 0
    expectancy = round(float(agg['net_pnl'] / total), 2) if total else 0

    daily = qs.filter(total_pnl__isnull=False).annotate(day=TruncDate('trade_date')) \
               .values('day').annotate(
                   daily_pnl=Sum('total_pnl'),
                   daily_volume=Sum(F('entry_price') * F('quantity'))
               ).order_by('day')
               
    daily_list = list(daily)
    total_days = len(daily_list)
    winning_days = sum(1 for d in daily_list if d['daily_pnl'] > 0)
    losing_days = sum(1 for d in daily_list if d['daily_pnl'] < 0)
    breakeven_days = total_days - winning_days - losing_days

    avg_daily_pnl = round(float(agg['net_pnl']) / total_days, 2) if total_days else 0
    total_vol = sum((d['daily_volume'] or 0) for d in daily_list)
    avg_daily_volume = float(total_vol / total_days) if total_days else 0

    daily_pnls = [float(d['daily_pnl']) for d in daily_list]
    consecutive_wins, consecutive_losses = _consecutive_streaks(daily_pnls)

    net_pnl_cumulative = []
    net_daily_pnl = []
    running_pnl = 0
    for d in daily_list:
        day_str = _fmt_date(d['day'])
        val = float(d['daily_pnl'] or 0)
        running_pnl += val
        net_pnl_cumulative.append({'date': day_str, 'pnl': round(running_pnl, 2)})
        net_daily_pnl.append({'date': day_str, 'pnl': round(val, 2)})

    if daily_list:
        sorted_daily_list = sorted(daily_list, key=lambda x: x['daily_pnl'] or 0)
        most_profit_dt = sorted_daily_list[-1]['day']
        least_profit_dt = sorted_daily_list[0]['day']
        most_profitable_day = _fmt_date(most_profit_dt)
        least_profitable_day = _fmt_date(least_profit_dt)
    else:
        most_profitable_day = "N/A"
        least_profitable_day = "N/A"

    hour_pnl = qs.filter(trade_time__isnull=False).annotate(
        hour=ExtractHour('trade_time')
    ).values('hour').annotate(
        avg_pnl=Avg('total_pnl')
    ).order_by('-avg_pnl')
    
    best_hour_data = hour_pnl.first()
    best_hour = "N/A"
    if best_hour_data and best_hour_data['hour'] is not None:
        hr = best_hour_data['hour']
        ampm = "AM" if hr < 12 else "PM"
        hr12 = hr if hr <= 12 else hr - 12
        hr12 = 12 if hr12 == 0 else hr12
        best_hour = f"{hr12}:00 {ampm}"

    session_counts = {
        'Early Morning': 0, 'Late Morning': 0, 'Midday': 0, 'Afternoon': 0, 'Closing': 0,
    }
    trades_with_time = list(qs.filter(trade_time__isnull=False).values('trade_time'))
    for t in trades_with_time:
        tt = t['trade_time']
        if tt:
            total_mins = tt.hour * 60 + tt.minute
            if 555 <= total_mins < 660: session_counts['Early Morning'] += 1
            elif 660 <= total_mins < 750: session_counts['Late Morning'] += 1
            elif 750 <= total_mins < 810: session_counts['Midday'] += 1
            elif 810 <= total_mins < 870: session_counts['Afternoon'] += 1
            elif 870 <= total_mins <= 930: session_counts['Closing'] += 1
            
    twt_count = len(trades_with_time)
    market_session_breakdown = []
    for s_name, s_count in session_counts.items():
        pct = round(s_count / twt_count * 100) if twt_count > 0 else 0
        market_session_breakdown.append({'session': s_name, 'percent_trades': pct})

    best_session = max(session_counts, key=session_counts.get) if twt_count else "N/A"

    strategy_effectiveness = []
    strat_qs = qs.filter(strategy__isnull=False).values('strategy__strategy_name').annotate(
        total_trades=Count('id'),
        wins=Count('id', filter=Q(total_pnl__gt=0))
    )
    for s in strat_qs:
        strat_win_rate = round(s['wins'] / s['total_trades'] * 100, 2) if s['total_trades'] else 0
        strategy_effectiveness.append({
            'strategy': s['strategy__strategy_name'] or 'Unknown',
            'win_rate': strat_win_rate
        })
        
    tr_cap = qs.annotate(capital=F('entry_price') * F('quantity'))
    agg_cap = tr_cap.aggregate(max=Max('capital'), min=Min('capital'), avg=Avg('capital'))
    max_cap_val = agg_cap['max'] or 0
    min_cap_val = agg_cap['min'] or 0
    avg_cap_val = agg_cap['avg'] or 0
    
    pnl_max_cap_trade = tr_cap.filter(capital=max_cap_val).first()
    pnl_min_cap_trade = tr_cap.filter(capital=min_cap_val).first()
    pnl_at_max_cap = pnl_max_cap_trade.total_pnl if pnl_max_cap_trade else 0
    pnl_at_min_cap = pnl_min_cap_trade.total_pnl if pnl_min_cap_trade else 0

    capital_usage = {
        'max_capital_used': float(max_cap_val),
        'min_capital_used': float(min_cap_val),
        'average_capital_used': round(float(avg_cap_val), 2),
        'pnl_at_max_capital': float(pnl_at_max_cap) if pnl_at_max_cap else 0,
        'pnl_at_min_capital': float(pnl_at_min_cap) if pnl_at_min_cap else 0,
    }

    agg_qty = qs.aggregate(max=Max('quantity'), min=Min('quantity'), avg=Avg('quantity'))
    max_qty_val = agg_qty['max'] or 0
    min_qty_val = agg_qty['min'] or 0
    avg_qty_val = agg_qty['avg'] or 0
    
    pnl_max_qty_trade = qs.filter(quantity=max_qty_val).first()
    pnl_min_qty_trade = qs.filter(quantity=min_qty_val).first()
    pnl_at_max_qty = pnl_max_qty_trade.total_pnl if pnl_max_qty_trade else 0
    pnl_at_min_qty = pnl_min_qty_trade.total_pnl if pnl_min_qty_trade else 0

    quantity_analysis = {
        'max_quantity': float(max_qty_val),
        'min_quantity': float(min_qty_val),
        'average_quantity': round(float(avg_qty_val), 2),
        'pnl_at_max_quantity': float(pnl_at_max_qty) if pnl_at_max_qty else 0,
        'pnl_at_min_quantity': float(pnl_at_min_qty) if pnl_at_min_qty else 0,
    }

    sym_qs = list(qs.values('symbol').annotate(
        count=Count('id'),
        pnl=Sum('total_pnl'),
        wins=Count('id', filter=Q(total_pnl__gt=0))
    ))
    if sym_qs:
        for s in sym_qs:
            s['win_rate'] = float(s['wins'] / s['count'] * 100) if s['count'] else 0
            s['pnl'] = s['pnl'] or Decimal('0')
            
        most_traded_sym = max(sym_qs, key=lambda x: x['count'])
        most_profitable_sym = max(sym_qs, key=lambda x: x['pnl'])
        least_profitable_sym = min(sym_qs, key=lambda x: x['pnl'])
        highest_win_sym = max(sym_qs, key=lambda x: x['win_rate'])
        lowest_win_sym = min(sym_qs, key=lambda x: x['win_rate'])
    
        symbol_frequency = {
            'most_traded_symbol': most_traded_sym['symbol'],
            'most_profitable_symbol': most_profitable_sym['symbol'],
            'least_profitable_symbol': least_profitable_sym['symbol'],
            'highest_win_rate_symbol': highest_win_sym['symbol'],
            'lowest_win_rate_symbol': lowest_win_sym['symbol'],
        }
    else:
        symbol_frequency = {}

    return {
        'performance': {
            'total_pnl': agg['net_pnl'],
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'trade_expectancy': expectancy,
            'avg_trade_pnl': agg['avg_trade_pnl'],
            'total_trades': total,
        },
        'net_pnl_cumulative': net_pnl_cumulative,
        'net_daily_pnl': net_daily_pnl,
        'performance_breakdown': {
            'trade_based_metrics': {
                'total_pnl': agg['net_pnl'],
                'average_winning_trade': agg['avg_win'],
                'average_losing_trade': agg['avg_loss'],
                'largest_winning_trade': agg['largest_win'],
                'largest_losing_trade': agg['largest_loss'],
                'profit_factor': profit_factor,
                'trade_expectancy': expectancy,
            },
            'day_based_metrics': {
                'total_trading_days': total_days,
                'winning_days': winning_days,
                'losing_days': losing_days,
                'breakeven_days': breakeven_days,
                'avg_daily_pnl': avg_daily_pnl,
                'avg_daily_volume': avg_daily_volume,
                'avg_holding_time': 'N/A',
            }
        },
        'time_metrics': {
            'trading_days': total_days,
            'consecutive_win_days': consecutive_wins,
            'consecutive_loss_days': consecutive_losses,
            'most_profitable_day': most_profitable_day,
            'least_profitable_day': least_profitable_day,
        },
        'duration_insights': {
            'avg_holding_duration': 'N/A',
            'best_session': best_session,
            'best_hour': best_hour,
            'most_common_duration': 'N/A',
            'trades_count': total,
        },
        'hold_time_vs_win_rate': [],
        'market_session_breakdown': market_session_breakdown,
        'strategy_effectiveness': strategy_effectiveness,
        'symbol_frequency': symbol_frequency,
        'capital_usage': capital_usage,
        'quantity_analysis': quantity_analysis,
    }


def get_risk_report_data(qs, capital_base_fallback=None):
    if qs.count() == 0:
        return {'message': 'No trades in the selected range.'}

    tr_cap = qs.annotate(capital=F('entry_price') * F('quantity'))
    agg = tr_cap.aggregate(
        max_capital_used=Max('capital'),
        min_capital_used=Min('capital'),
        avg_capital_used=Avg('capital'),
        max_qty=Max('quantity'),
        avg_qty=Avg('quantity'),
    )

    daily = qs.filter(total_pnl__isnull=False).annotate(day=TruncDate('trade_date')) \
               .values('day').annotate(
                   daily_pnl=Sum('total_pnl'),
               ).order_by('day')
               
    daily_pnls = []
    for d in daily:
        day_str = _fmt_date(d['day'])
        daily_pnls.append({'date': day_str, 'pnl': float(d['daily_pnl'] or 0)})

    worst_losing_day = min((d['pnl'] for d in daily_pnls), default=0)

    cumulative = []
    running = 0
    for d in daily_pnls:
        running += d['pnl']
        cumulative.append({'date': d['date'], 'cum_pnl': running})

    max_dd = 0
    drawdowns = []
    peak = 0
    drawdown_curve = []
    
    recovery_times = []
    current_recovery_sessions = 0
    in_drawdown = False

    for c in cumulative:
        if c['cum_pnl'] > peak:
            peak = c['cum_pnl']
            if in_drawdown:
                recovery_times.append(current_recovery_sessions)
                in_drawdown = False
                current_recovery_sessions = 0
        else:
            in_drawdown = True
            current_recovery_sessions += 1

        dd = peak - c['cum_pnl']
        drawdown_curve.append({'date': c['date'], 'drawdown': round(dd, 2)})
        if dd > 0:
            drawdowns.append(dd)
        if dd > max_dd:
            max_dd = dd

    avg_dd = sum(drawdowns) / len(drawdowns) if drawdowns else 0
    avg_recovery_time = round(sum(recovery_times) / len(recovery_times)) if recovery_times else 0

    base_capital = float(capital_base_fallback or agg['max_capital_used'] or 1)
    
    returns = [d['pnl'] / base_capital for d in daily_pnls]
    if len(returns) > 1:
        mean_return = sum(returns) / len(returns)
        variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
        volatility_pct = (variance ** 0.5) * 100
    else:
        volatility_pct = 0.0

    max_dd_pct = (max_dd / base_capital) * 100 if base_capital else 0
    avg_dd_pct = (avg_dd / base_capital) * 100 if base_capital else 0

    return {
        'max_drawdown': {
            'amount': round(max_dd, 2),
            'percentage': round(max_dd_pct, 2)
        },
        'average_drawdown': {
            'amount': round(avg_dd, 2),
            'percentage': round(avg_dd_pct, 2)
        },
        'worst_losing_day': round(worst_losing_day, 2),
        'recovery_time': avg_recovery_time,
        'return_volatility': round(volatility_pct, 2),
        'drawdown_curve': drawdown_curve,
        'max_capital_used': agg['max_capital_used'],
        'min_capital_used': agg['min_capital_used'],
        'avg_capital_used': agg['avg_capital_used'],
        'max_quantity': agg['max_qty'],
        'avg_quantity': agg['avg_qty'],
    }


def get_behavior_report_data(user, qs, filters):
    from insights.services import calculate_metrics
    from insights.serializers import MetricsSnapshotSerializer
    from discipline.models import ViolationsLog
    from mistakes.models import TradeMistake
    
    snapshot = calculate_metrics(user)
    snapshot_data = MetricsSnapshotSerializer(snapshot).data

    kpis = {
        'DIS': {'value': snapshot.di_score, 'trend': 'Stable'},
        'VMI': {'value': snapshot.vmi_score, 'trend': snapshot.vmi_level},
        'DRT': {'value': float(snapshot.drt_days), 'trend': 'Stable'},
    }
    
    total_trades = qs.count()
    
    violated_trade_ids = ViolationsLog.objects.filter(
        user=user, 
        trade__in=qs, 
        violation_type='hard'
    ).values_list('trade_id', flat=True).distinct()
    
    violated_count = len(violated_trade_ids)
    eci = round(((total_trades - violated_count) / total_trades * 100), 1) if total_trades > 0 else 100.0
    kpis['ECI'] = {'value': eci, 'trend': 'Stable'}

    from_date = filters.get('from')
    to_date = filters.get('to')
    
    violations_qs = ViolationsLog.objects.filter(user=user)
    if from_date:
        violations_qs = violations_qs.filter(violated_at__gte=from_date)
    if to_date:
        violations_qs = violations_qs.filter(violated_at__lte=to_date)
        
    timeline_data = list(violations_qs.annotate(date=TruncDate('violated_at'))
                                      .values('date')
                                      .annotate(count=Count('id'))
                                      .order_by('date'))
                                      
    violations_timeline = []
    for t in timeline_data:
        day_str = _fmt_date(t['date'])
        violations_timeline.append({'date': day_str, 'violations': t['count']})

    trade_ids = qs.values_list('id', flat=True)
    mistakes_qs = TradeMistake.objects.filter(trade__in=trade_ids).select_related('mistake', 'trade')
    
    heatmap_data = {}
    mistake_stats = {}
    total_mistake_losses = 0
    
    for tm in mistakes_qs:
        name = tm.mistake.mistake_name
        trade_date = tm.trade.trade_date
        day_str = _fmt_date(trade_date)
        pnl = float(tm.trade.total_pnl or 0)
        
        if name not in heatmap_data:
            heatmap_data[name] = {}
        if day_str not in heatmap_data[name]:
            heatmap_data[name][day_str] = 0
        heatmap_data[name][day_str] += 1
        
        if name not in mistake_stats:
            mistake_stats[name] = {'count': 0, 'loss': 0}
        mistake_stats[name]['count'] += 1
        
        if pnl < 0:
            loss_val = abs(pnl)
            mistake_stats[name]['loss'] += loss_val
            total_mistake_losses += loss_val

    formatted_heatmap = []
    for mistake_name, dates in heatmap_data.items():
        formatted_heatmap.append({
            'mistake_type': mistake_name,
            'occurrences': dates
        })

    top_recurring = []
    for name, stats in mistake_stats.items():
        pct = round((stats['loss'] / total_mistake_losses * 100), 1) if total_mistake_losses > 0 else 0
        top_recurring.append({
            'name': name,
            'occurrences': stats['count'],
            'loss_percent': pct
        })
    top_recurring.sort(key=lambda x: x['loss_percent'], reverse=True)

    insight_text = "Discipline is stable. Keep focusing on executing your edge."
    if eci < 80:
        insight_text = "ECI has dropped below 80%. Most losses occurred on days with multiple rule violations. Pause trading after your first hard violation."
    elif total_mistake_losses > 0 and top_recurring:
        insight_text = f"Mistakes cluster heavily around {top_recurring[0]['name']}, contributing to {top_recurring[0]['loss_percent']}% of your losses. Review your triggers before the next session."

    rule_category_counts = violations_qs.values('rule__category').annotate(count=Count('id'))
    
    categories = ['risk', 'entry', 'exit', 'process', 'psychology']
    adherence = {}
    
    for cat in categories:
        adherence[cat.capitalize()] = 100.0
        
    if total_trades > 0:
        for rc in rule_category_counts:
            cat_name = (rc['rule__category'] or 'Unknown').capitalize()
            v_count = rc['count']
            pct_violated = (v_count / total_trades) * 100
            adherence[cat_name] = max(0.0, round(100.0 - pct_violated, 1))

    return {
        'kpis': kpis,
        'snapshot': snapshot_data,
        'violations_timeline': violations_timeline,
        'mistake_heatmap': formatted_heatmap,
        'top_recurring_mistakes': top_recurring,
        'behavior_insight': insight_text,
        'rule_adherence': adherence
    }


def get_strategy_report_data(qs):
    from strategies.models import Strategy
    
    strategy_ids = qs.values_list('strategy_id', flat=True).distinct()
    results = []

    for sid in strategy_ids:
        if not sid:
            continue
        strategy_trades = qs.filter(strategy_id=sid)
        total = strategy_trades.count()
        agg = strategy_trades.aggregate(
            total_pnl=Sum('total_pnl'),
            gross_profit=Sum('total_pnl', filter=Q(total_pnl__gt=0)),
            gross_loss=Sum('total_pnl', filter=Q(total_pnl__lt=0)),
        )
        wins = strategy_trades.filter(total_pnl__gt=0).count()
        gp = agg['gross_profit'] or Decimal('0')
        gl = abs(agg['gross_loss'] or Decimal('0'))

        try:
            strategy_name = Strategy.objects.get(pk=sid).strategy_name
        except Strategy.DoesNotExist:
            strategy_name = 'Unknown'

        results.append({
            'strategy_id': sid,
            'strategy_name': strategy_name,
            'total_trades': total,
            'win_rate': round(wins / total * 100, 2) if total else 0,
            'total_pnl': agg['total_pnl'],
            'profit_factor': round(float(gp / gl), 2) if gl else 0,
        })

    results.sort(key=lambda x: float(x['total_pnl'] or 0), reverse=True)
    return results


def get_journal_report_data(user, qs, filters):
    from journal.models import DailyJournal, PsychologyLog, SessionRecap
    
    from_date = filters.get('from')
    to_date = filters.get('to')

    def date_filter(logs, field='journal_date'):
        if from_date:
            logs = logs.filter(**{f'{field}__gte': from_date})
        if to_date:
            logs = logs.filter(**{f'{field}__lte': to_date})
        return logs

    journals = date_filter(DailyJournal.objects.filter(user=user))
    psych_logs = date_filter(PsychologyLog.objects.filter(user=user), 'log_date')
    recaps = date_filter(SessionRecap.objects.filter(user=user), 'recap_date')

    psych_agg = psych_logs.aggregate(
        avg_confidence=Avg('confidence_before'),
        avg_satisfaction=Avg('satisfaction_after'),
    )

    emotion_counts = list(psych_logs.values('emotional_state').annotate(
        count=Count('id')
    ).order_by('-count'))
    
    emotion_frequency = {item['emotional_state']: item['count'] for item in emotion_counts}
    most_common_emotion = emotion_counts[0]['emotional_state'] if emotion_counts else None

    logs_with_trades = psych_logs.filter(trade__isnull=False).select_related('trade')
    
    confidences = []
    satisfactions = []
    pnls = []
    emotion_impact = {}

    for log in logs_with_trades:
        pnl = float(log.trade.total_pnl or 0)
        conf = log.confidence_before
        sat = log.satisfaction_after
        state = log.emotional_state

        if conf is not None:
            confidences.append(conf)
            pnls.append(pnl)
        if sat is not None:
            satisfactions.append(sat)
            
        if state not in emotion_impact:
            emotion_impact[state] = 0
        emotion_impact[state] += pnl

    def calc_correlation(x, y):
        n = len(x)
        if n < 2: return 0.0
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi*yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi*xi for xi in x)
        sum_y2 = sum(yi*yi for yi in y)
        
        numerator = (n * sum_xy) - (sum_x * sum_y)
        denominator = math.sqrt((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))
        return round(numerator / denominator, 2) if denominator else 0.0

    conf_correlation = calc_correlation(confidences, pnls)
    sat_correlation = calc_correlation(satisfactions, pnls)

    traded_dates = qs.values_list('trade_date', flat=True).distinct()
    journaled_dates = journals.values_list('journal_date', flat=True).distinct()
    
    traded_set = set(traded_dates)
    journaled_set = set(journaled_dates)
    
    days_traded = len(traded_set)
    days_journaled = len(traded_set.intersection(journaled_set))
    completion_rate = round((days_journaled / days_traded * 100), 1) if days_traded > 0 else 0
    missed_days = days_traded - days_journaled

    recap_summary = recaps.values('outcome').annotate(count=Count('id'))
    recap_dist = {r['outcome']: r['count'] for r in recap_summary}

    return {
        'journal_discipline': {
            'completion_rate': completion_rate,
            'current_streak': user.current_streak,
            'longest_streak': user.longest_streak,
            'missed_journaling_days': missed_days,
            'journal_count': journals.count(),
        },
        'psychology_summary': {
            'avg_confidence': psych_agg['avg_confidence'],
            'avg_satisfaction': psych_agg['avg_satisfaction'],
            'most_common_emotion': most_common_emotion,
            'confidence_correlation': conf_correlation,
            'satisfaction_correlation': sat_correlation,
            'emotion_frequency': emotion_frequency,
            'emotional_impact_pnl': emotion_impact,
        },
        'session_recap_summary': {
            'good': recap_dist.get('good', 0),
            'neutral': recap_dist.get('neutral', 0),
            'bad': recap_dist.get('bad', 0),
        },
    }


def get_mistakes_report_data(qs):
    from mistakes.models import TradeMistake
    from journal.models import PsychologyLog
    
    trade_ids = qs.values_list('id', flat=True)
    if not trade_ids:
        return {'message': 'No trades in the selected range.'}

    mistakes_qs = TradeMistake.objects.filter(trade__in=trade_ids).select_related('mistake', 'trade')
    
    mistake_stats = {}
    total_cost = 0
    mistake_count = 0

    for tm in mistakes_qs:
        name = tm.mistake.mistake_name
        pnl = float(tm.trade.total_pnl or 0)
        
        if name not in mistake_stats:
            mistake_stats[name] = {'count': 0, 'loss_contribution': 0}
            
        mistake_stats[name]['count'] += 1
        mistake_count += 1
        
        if pnl < 0:
            loss_val = abs(pnl)
            mistake_stats[name]['loss_contribution'] += loss_val
            total_cost += loss_val

    most_frequent = None
    max_freq = 0
    for name, stats in mistake_stats.items():
        if stats['count'] > max_freq:
            max_freq = stats['count']
            most_frequent = name

    avg_cost = total_cost / mistake_count if mistake_count > 0 else 0

    psych_logs = PsychologyLog.objects.filter(
        trade__in=trade_ids, 
        pressure_source__isnull=False
    ).select_related('trade')
    
    trigger_analysis = {}
    for log in psych_logs:
        trigger = log.pressure_source
        pnl = float(log.trade.total_pnl or 0)
        
        if trigger not in trigger_analysis:
            trigger_analysis[trigger] = {'trades': 0, 'total_pnl': 0}
            
        trigger_analysis[trigger]['trades'] += 1
        trigger_analysis[trigger]['total_pnl'] += pnl

    for t in trigger_analysis:
        trigger_analysis[t]['avg_pnl'] = round(trigger_analysis[t]['total_pnl'] / trigger_analysis[t]['trades'], 2)

    return {
        'mistake_frequency': {name: stats['count'] for name, stats in mistake_stats.items()},
        'loss_contribution': {name: round(stats['loss_contribution'], 2) for name, stats in mistake_stats.items()},
        'most_frequent_mistake': most_frequent,
        'total_mistake_cost': round(total_cost, 2),
        'avg_cost_per_mistake': round(avg_cost, 2),
        'clustering_pattern_detected': mistake_count > 3,
        'trigger_analysis': trigger_analysis
    }


def get_overview_report_data(user, qs, filters):
    from django.utils.timezone import localdate
    from discipline.models import DisciplineSession, ViolationsLog
    from tradelog.models import Trade
    from mistakes.models import TradeMistake
    from insights.services import calculate_metrics
    import calendar

    today = localdate()
    first_day_of_month = today.replace(day=1)
    if first_day_of_month.month == 1:
        prev_month_first = first_day_of_month.replace(year=first_day_of_month.year - 1, month=12)
    else:
        prev_month_first = first_day_of_month.replace(month=first_day_of_month.month - 1)
    
    _, prev_month_days = calendar.monthrange(prev_month_first.year, prev_month_first.month)
    prev_month_last = prev_month_first.replace(day=prev_month_days)

    from_date_str = filters.get('from')
    to_date_str = filters.get('to')

    if from_date_str and to_date_str:
        # Custom date range: compare this range vs previous same-length range
        from datetime import datetime as dt_
        from_d = dt_.strptime(from_date_str, '%Y-%m-%d').date()
        to_d = dt_.strptime(to_date_str, '%Y-%m-%d').date()
        period_days = (to_d - from_d).days or 1
        prev_from = from_d - timedelta(days=period_days + 1)
        prev_to = from_d - timedelta(days=1)
        vsText_label = "vs previous period"

        this_period_qs = Trade.objects.filter(
            user=user, deleted_at__isnull=True,
            trade_date__gte=from_d, trade_date__lte=to_d, total_pnl__isnull=False
        )
        prev_period_qs = Trade.objects.filter(
            user=user, deleted_at__isnull=True,
            trade_date__gte=prev_from, trade_date__lte=prev_to, total_pnl__isnull=False
        )
    else:
        # No filter: detect the most recent month that has actual trades
        all_trades_qs = Trade.objects.filter(user=user, deleted_at__isnull=True, total_pnl__isnull=False)
        latest_trade = all_trades_qs.order_by('-trade_date').first()

        if latest_trade:
            latest_date = latest_trade.trade_date
            # "This month" = the calendar month of the latest trade
            ref_first = latest_date.replace(day=1)
            if ref_first.month == 1:
                prev_ref_first = ref_first.replace(year=ref_first.year - 1, month=12)
            else:
                prev_ref_first = ref_first.replace(month=ref_first.month - 1)
            _, ref_month_days = calendar.monthrange(ref_first.year, ref_first.month)
            _, prev_ref_days = calendar.monthrange(prev_ref_first.year, prev_ref_first.month)
            ref_last = ref_first.replace(day=ref_month_days)
            prev_ref_last = prev_ref_first.replace(day=prev_ref_days)
            vsText_label = "vs last month"
        else:
            # No trades at all — fall back to today
            ref_first = first_day_of_month
            ref_last = today
            prev_ref_first = prev_month_first
            prev_ref_last = prev_month_last
            vsText_label = "vs last month"

        this_period_qs = all_trades_qs.filter(trade_date__gte=ref_first, trade_date__lte=ref_last)
        prev_period_qs = all_trades_qs.filter(trade_date__gte=prev_ref_first, trade_date__lte=prev_ref_last)

    # Net P&L
    closed_qs = qs.filter(total_pnl__isnull=False)
    this_pnl = closed_qs.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    this_period_pnl = this_period_qs.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')
    prev_pnl = prev_period_qs.aggregate(total=Sum('total_pnl'))['total'] or Decimal('0')

    pnl_pct_change = 0
    if prev_pnl != 0:
        pnl_pct_change = round(((this_period_pnl - prev_pnl) / abs(prev_pnl)) * 100, 1)
    elif this_period_pnl > 0:
        pnl_pct_change = 100.0

    # Win Rate
    def calc_win_rate(query):
        total = query.count()
        if total == 0: return 0.0
        wins = query.filter(total_pnl__gt=0).count()
        return round((wins / total) * 100, 1)

    this_wr = calc_win_rate(this_period_qs)
    prev_wr = calc_win_rate(prev_period_qs)
    wr_change = round(this_wr - prev_wr, 1)

    # General specific metrics (from whole qs or filtered qs based on standard report)
    total_trades = closed_qs.count()
    wins = closed_qs.filter(total_pnl__gt=0).count()
    win_rate = round(wins / total_trades * 100, 1) if total_trades else 0.0

    gross_profit = closed_qs.aggregate(gp=Sum('total_pnl', filter=Q(total_pnl__gt=0)))['gp'] or Decimal('0')
    gross_loss = abs(closed_qs.aggregate(gl=Sum('total_pnl', filter=Q(total_pnl__lt=0)))['gl'] or Decimal('0'))
    profit_factor = round(float(gross_profit / gross_loss), 1) if gross_loss else 0.0

    avg_win = closed_qs.aggregate(avg=Avg('total_pnl', filter=Q(total_pnl__gt=0)))['avg'] or Decimal('0')
    avg_loss = abs(closed_qs.aggregate(avg=Avg('total_pnl', filter=Q(total_pnl__lt=0)))['avg'] or Decimal('0'))
    
    daily = closed_qs.annotate(day=TruncDate('trade_date')) \
               .values('day').annotate(daily_pnl=Sum('total_pnl')).order_by('day')
               
    daily_list = list(daily)
    total_days = len(daily_list)
    winning_days = sum(1 for d in daily_list if d['daily_pnl'] > 0)
    day_win_rate = round((winning_days / total_days) * 100, 1) if total_days else 0.0

    net_pnl_cumulative = []
    net_daily_pnl = []
    running_pnl = 0
    for d in daily_list:
        day_str = _fmt_date(d['day'])
        val = float(d['daily_pnl'] or 0)
        running_pnl += val
        net_pnl_cumulative.append({'date': day_str, 'pnl': round(running_pnl, 2)})
        net_daily_pnl.append({'date': day_str, 'pnl': round(val, 2)})

    chartData = {
        'netPnlCumulative': net_pnl_cumulative,
        'netDailyPnl': net_daily_pnl
    }

    # Session Health
    # Using the most active discipline session from today, similar to get_active_session logic
    today_session = DisciplineSession.objects.filter(user=user).order_by('-session_date').first()
    if today_session and today_session.session_date == today:
        session_color = today_session.session_state
        session_status_label = "Normal" if session_color == 'green' else ("Warning" if session_color == 'yellow' else "Locked")
        today_trades = Trade.objects.filter(user=user, trade_date=today, deleted_at__isnull=True).count()
        today_violations = today_session.violations_count
        today_mistakes = TradeMistake.objects.filter(trade__user=user, trade__trade_date=today).count()
        journal_completed = today_session.journal_completed
    else:
        session_color = "green"
        session_status_label = "Normal"
        today_trades = Trade.objects.filter(user=user, trade_date=today, deleted_at__isnull=True).count()
        today_violations = 0
        today_mistakes = TradeMistake.objects.filter(trade__user=user, trade__trade_date=today).count()
        journal_completed = False

    sessionHealth = {
        'status': session_status_label,
        'color': session_color,
        'tradesToday': today_trades,
        'rulesViolated': today_violations,
        'mistakesLogged': today_mistakes,
        'journalCompleted': journal_completed
    }

    # Discipline vs Performance
    green_session_ids = list(DisciplineSession.objects.filter(user=user, peak_state='green').values_list('id', flat=True))
    non_green_session_ids = list(DisciplineSession.objects.filter(user=user).exclude(peak_state='green').values_list('id', flat=True))

    green_trades = qs.filter(session_id__in=green_session_ids)
    non_green_trades = qs.filter(session_id__in=non_green_session_ids)

    def performance_stats(t_qs):
        t_count = t_qs.count()
        win_r = 0.0
        avg_r = 0.0
        drawdown_pct = 0.0
        if t_count > 0:
            w_count = t_qs.filter(total_pnl__gt=0).count()
            win_r = round((w_count / t_count) * 100, 1)
            # R-multiple proxy using raw average P&L or actual R... (using avg P&L / avg Loss, or 0)
            avg_p = t_qs.aggregate(total=Avg('total_pnl'))['total'] or Decimal('0')
            # For simplicity, calculate avg R assuming risk is 1R. Avg return approximation:
            avg_loss_val = abs(t_qs.aggregate(avg_loss=Avg('total_pnl', filter=Q(total_pnl__lt=0)))['avg_loss'] or Decimal('1'))
            avg_r = round(float(avg_p / avg_loss_val) if avg_loss_val else float(avg_p), 1)

            # Drawdown proxy for this set
            daily_set = t_qs.annotate(day=TruncDate('trade_date')) \
                           .values('day').annotate(daily_pnl=Sum('total_pnl')).order_by('day')
            peak = 0
            running = 0
            max_dd = 0
            for d in daily_set:
                running += float(d['daily_pnl'] or 0)
                if running > peak: peak = running
                dd = peak - running
                if dd > max_dd: max_dd = dd
                
            base_capital = float(user.trading_capital or 1)
            drawdown_pct = round((max_dd / base_capital) * 100, 1) if base_capital else 0.0

        return {
            'winRate': win_r,
            'avgReturn': avg_r,
            'drawdown': -drawdown_pct if drawdown_pct else 0.0
        }

    disciplineVsPerformance = {
        'disciplined': performance_stats(green_trades),
        'undisciplined': performance_stats(non_green_trades)
    }

    # Exclusive Metrics
    snapshot = calculate_metrics(user)
    exclusiveMetrics = {
        'di': float(snapshot.di_score),
        'vmi': snapshot.vmi_level,
        'drt': float(snapshot.drt_days),
        'tpr': float(snapshot.tpr_score),
        'fie': float(snapshot.fie_amount),
        'ovr': float(snapshot.ovr_score),
        'eci': float(snapshot.eci_amount),
        'cas': float(snapshot.cas_score),
        'dae': float(snapshot.dae_r), # discipline adjusted expectancy
        'smi': snapshot.smi_status.capitalize() if snapshot.smi_status else 'Dev',
        'ddr': snapshot.ddr_level,
        'cpi': float(snapshot.cpi_score) if snapshot.cpi_score else 100.0
    }

    return {
        'netPnl': {
            'value': float(this_pnl),
            'percentChange': pnl_pct_change,
            'vsText': vsText_label
        },
        'tradeWinPercent': {
            'value': win_rate,
            'percentChange': wr_change,
            'vsText': "improvement" if wr_change >= 0 else "decline"
        },
        'profitFactor': profit_factor,
        'dayWinPercent': day_win_rate,
        'avgWin': float(avg_win),
        'avgLoss': float(avg_loss),
        'chartData': chartData,
        'sessionHealth': sessionHealth,
        'disciplineVsPerformance': disciplineVsPerformance,
        'exclusiveMetrics': exclusiveMetrics
    }
