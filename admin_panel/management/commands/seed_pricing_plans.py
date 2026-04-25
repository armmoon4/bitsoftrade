"""
admin_panel/management/commands/seed_pricing_plans.py

Seeds the four fixed pricing plan rows from your current frontend cards.
Run ONCE after migrating:

    python manage.py seed_pricing_plans

Safe to re-run — uses update_or_create so it won't duplicate rows.
"""

from django.core.management.base import BaseCommand
from admin_panel.models import PricingPlan


PLANS = [
    {
        'card_key':      'discipline_tools',
        'name':          'Discipline Tools',
        'badge':         'Behavior Control & Prevention',
        'tagline':       'Traders who want to control activity, reduce overtrading, and introduce structure.',
        'cta_label':     'Activate Discipline Tools',
        'footer_note':   'Discipline infrastructure only. No learning included.',
        'price':         499,        # monthly price  (₹499/month)
        'price_yearly':  4999,       # yearly price — set your actual annual amount here
        'billing_cycle': 'monthly',
        'is_popular':    False,
        'is_active':     True,
        'features': [
            'Discipline Guard',
            'Behavior-First Journal',
            'Session & Rule Monitoring',
            'Behavior-Based Reports',
            'Strategy Frameworks',
            'AI Based Insights',
        ],
        'display_order': 1,
    },
    {
        'card_key':      'learning_hub',
        'name':          'Learning Hub',
        'badge':         'Structured Trading Education',
        'tagline':       'Traders building long-term understanding and process.',
        'cta_label':     'Unlock Learning Hub',
        'footer_note':   'Educational access only. No discipline tools included.',
        'price':         2999,       # ₹2,999 / 6 months
        'price_yearly':  None,
        'billing_cycle': 'biannual',
        'is_popular':    False,
        'is_active':     True,
        'features': [
            'Full Learning Hub Access',
            'Risk & Discipline Modules',
            'Structured Curriculum',
            'Access for 6 months',
        ],
        'display_order': 2,
    },
    {
        'card_key':      'combo_monthly',
        'name':          'Monthly Combo',
        'badge':         'Structure + Understanding',
        'tagline':       'For traders who want both structure and understanding, working together.',
        'cta_label':     'Get Complete System',
        'footer_note':   'Ideal for trying the full system before committing long-term.',
        'price':         2799,       # ₹2,799
        'price_yearly':  None,
        'billing_cycle': 'monthly',
        'is_popular':    False,
        'is_active':     True,
        'features': [
            '1 month Discipline Tools',
            '6 months Learning Hub',
        ],
        'display_order': 3,
    },
    {
        'card_key':      'combo_annual',
        'name':          'Annual Combo',
        'badge':         'Structure + Understanding',
        'tagline':       'Best value for traders committed to consistency.',
        'cta_label':     'Commit for a Year',
        'footer_note':   '',
        'price':         6999,       # ₹6,999/yr
        'price_yearly':  None,
        'billing_cycle': 'annual',
        'is_popular':    True,
        'is_active':     True,
        'features': [
            '12 months Discipline Tools',
            '6 months Learning Hub',
        ],
        'display_order': 4,
    },
]


class Command(BaseCommand):
    help = 'Seed the four fixed pricing plan rows.'

    def handle(self, *args, **kwargs):
        for plan_data in PLANS:
            card_key = plan_data.pop('card_key')
            obj, created = PricingPlan.objects.update_or_create(
                card_key=card_key,
                defaults=plan_data,
            )
            action = 'Created' if created else 'Updated'
            self.stdout.write(f'  {action}: {card_key}')

        self.stdout.write(self.style.SUCCESS('Done — pricing plans seeded.'))
