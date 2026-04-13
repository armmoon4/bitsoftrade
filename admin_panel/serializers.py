"""
admin_panel/serializers.py
──────────────────────────
Plain-dict serialisation helpers for models that don't use DRF ModelSerializer.
Keep these pure functions: input = model instance, output = dict.
"""


def review_to_dict(r):
    return {
        'id':            str(r.id),
        'reviewer_name': r.reviewer_name,
        'rating':        r.rating,
        'review_text':   r.review_text,
        'is_visible':    r.is_visible,
        'display_order': r.display_order,
        'created_at':    r.created_at,
        'updated_at':    r.updated_at,
    }


def plan_to_dict(p):
    return {
        'id':            str(p.id),
        'name':          p.name,
        'price':         str(p.price),
        'billing_cycle': p.billing_cycle,
        'is_popular':    p.is_popular,
        'is_active':     p.is_active,
        'features':      p.features,
        'display_order': p.display_order,
        'created_at':    p.created_at,
        'updated_at':    p.updated_at,
    }


def broadcast_to_dict(b):
    return {
        'id':              str(b.id),
        'title':           b.title,
        'message':         b.message,
        'recipients':      b.recipients,
        'delivered_count': b.delivered_count,
        'sent_by':         b.sent_by_admin.full_name if b.sent_by_admin else None,
        'created_at':      b.created_at,
    }
