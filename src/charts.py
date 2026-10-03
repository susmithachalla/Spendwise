"""Exact per-currency summaries and chart series shared by income and expenses."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from src.currencies import decimal_amount, money


def build_charts(rows, categories):
    # Decimal totals also handle stored currency precision if metadata later changes.
    totals = defaultdict(Decimal)
    precisions = {}
    for row in rows:
        code = row['currency']
        totals[code] += decimal_amount(row['amount_minor'], row['fraction_digits'])
        precisions[code] = max(precisions.get(code, 0), row['fraction_digits'])
    summaries = [{'currency': code, 'display': money(int(total.scaleb(precisions[code])), code, precisions[code])}
                 for code, total in sorted(totals.items())]
    charts = []
    for summary in summaries:
        code = summary['currency']
        groups = {key: defaultdict(Decimal) for key in ('category', 'date', 'month')}
        for row in rows:
            if row['currency'] == code:
                amount = decimal_amount(row['amount_minor'], row['fraction_digits'])
                groups['category'][row['category']] += amount
                groups['date'][row['expense_date']] += amount
                groups['month'][row['expense_date'][:7]] += amount
        chart = dict(summary)
        for mode, amounts in groups.items():
            maximum = max(amounts.values())
            chart[mode] = [
                {'label': label, 'amount': str(amount),
                 'display': money(int(amount.scaleb(precisions[code])), code, precisions[code]),
                 'width': float(amount / maximum * 100) if maximum else 0}
                for label, amount in sorted(amounts.items())]
        offset = 0
        for bar in chart['category']:
            share = Decimal(bar['amount']) / totals[code] * 100 if totals[code] else Decimal(0)
            bar.update(percent=f'{share:.1f}', share=float(share), offset=-offset,
                       color=categories.get(bar['label'], {'color': '#8b8583'})['color'])
            offset += float(share)
        # Axis steps use whole minor units, including for zero-decimal currencies.
        for mode in ('date', 'month'):
            maximum_minor = max(int(Decimal(bar['amount']).scaleb(precisions[code])) for bar in chart[mode])
            step = max(1, (maximum_minor + 3) // 4)
            ticks = [money(step * i, code, precisions[code]) for i in range(4, -1, -1)]
            chart['ticks' if mode == 'date' else 'month_ticks'] = ticks
            for bar in chart[mode]:
                bar['height'] = float(Decimal(bar['amount']).scaleb(precisions[code]) / (step * 4) * 100)
                parsed = date.fromisoformat(bar['label'] + ('-01' if mode == 'month' else ''))
                bar['short_date'] = parsed.strftime('%b' if mode == 'month' else '%b %d')
                bar['year'] = parsed.year
        charts.append(chart)
    return summaries, charts
