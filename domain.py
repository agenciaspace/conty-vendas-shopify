"""Integer-cent attribution ledger; refunds may precede their order."""
import json
from core import Problem, require, text, integer, iso

def key(*parts): return json.dumps(parts, separators=(',', ':'))

def attribution(state, shop, coupon, utm):
    config = state.setdefault('shops', {}).get(shop, {'coupons': {}, 'creators': []})
    coupon_creator = config['coupons'].get(coupon.upper()) if coupon else None
    utm_creator = utm if utm in config['creators'] else None
    if coupon_creator:
        return {'creator_id': coupon_creator, 'rule': 'valid_coupon_wins', 'coupon_creator': coupon_creator, 'utm_creator': utm_creator}
    if utm_creator:
        return {'creator_id': utm_creator, 'rule': 'valid_utm_fallback', 'coupon_creator': None, 'utm_creator': utm_creator}
    return {'creator_id': None, 'rule': 'no_known_creator', 'coupon_creator': None, 'utm_creator': None}

def reconcile(state, order):
    refunds = [r for r in state.setdefault('refunds', {}).values() if r['shop'] == order['shop'] and r['order_id'] == order['id']]
    remaining = order['total_cents']
    for refund in refunds:
        applied = min(remaining, refund['amount_cents'])
        remaining -= applied
        refund.update(state='applied', applied_cents=applied, excess_cents=refund['amount_cents'] - applied)
    order.update(refunded_cents=order['total_cents'] - remaining, net_cents=remaining,
                 attributed_cents=remaining if order['attribution']['creator_id'] else 0,
                 status='refunded' if remaining == 0 else ('partially_refunded' if refunds else 'paid'), refunds=refunds)
    order['ledger'] = [{'kind': 'sale', 'event_id': order['id'], 'cents': order['total_cents']}] + [
        {'kind': 'refund', 'event_id': r['id'], 'cents': -r['applied_cents']} for r in refunds]
    return order

def dispatch(state, method, path, data, now):
    orders, refunds = state.setdefault('orders', {}), state.setdefault('refunds', {})
    if method == 'POST' and path == '/creators':
        shop, creator, coupon = text(data, 'shop'), text(data, 'id'), text(data, 'coupon').upper()
        config = state.setdefault('shops', {}).setdefault(shop, {'creators': [], 'coupons': {}})
        require(coupon not in config['coupons'] or config['coupons'][coupon] == creator, 'coupon belongs to another creator', 409)
        if creator not in config['creators']: config['creators'].append(creator)
        config['coupons'][coupon] = creator
        return {'shop': shop, 'creator_id': creator, 'coupon': coupon}
    if method == 'POST' and path == '/orders':
        shop, ident = text(data, 'shop'), text(data, 'id')
        require(data.get('status') == 'paid', 'only paid order events are accepted; use /refunds for refunds')
        total = integer(data, 'total_cents', 1)
        coupon, utm = data.get('coupon', ''), data.get('utm_creator', '')
        require(isinstance(coupon, str) and isinstance(utm, str), 'coupon and utm_creator must be strings')
        raw = {'shop': shop, 'id': ident, 'total_cents': total, 'coupon': coupon.strip().upper(), 'utm_creator': utm.strip(), 'status': 'paid'}
        existing = orders.get(key(shop, ident))
        if existing:
            require(existing['original'] == raw, 'conflicting order replay', 409)
            return reconcile(state, existing)
        order = {'id': ident, 'shop': shop, 'total_cents': total, 'original': raw,
                 'received_at': iso(now), 'attribution': attribution(state, shop, raw['coupon'], raw['utm_creator'])}
        orders[key(shop, ident)] = order
        return reconcile(state, order)
    if method == 'POST' and path == '/refunds':
        shop, ident, order_id = text(data, 'shop'), text(data, 'id'), text(data, 'order_id')
        amount = integer(data, 'amount_cents', 1)
        original = {'shop': shop, 'id': ident, 'order_id': order_id, 'amount_cents': amount}
        existing = refunds.get(key(shop, ident))
        if existing:
            require(existing['original'] == original, 'conflicting refund replay', 409)
        else:
            refunds[key(shop, ident)] = {**original, 'original': original, 'state': 'pending',
                                         'received_at': iso(now), 'applied_cents': 0, 'excess_cents': 0}
        order = orders.get(key(shop, order_id))
        if order: reconcile(state, order)
        return refunds[key(shop, ident)]
    parts = path.strip('/').split('/')
    if method == 'GET' and len(parts) == 3 and parts[0] == 'orders':
        order = orders.get(key(parts[1], parts[2]))
        require(order is not None, 'order not found', 404)
        return reconcile(state, order)
    if method == 'GET' and len(parts) == 3 and parts[0] == 'refunds':
        result = refunds.get(key(parts[1], parts[2]))
        require(result is not None, 'refund not found', 404)
        return result
    raise Problem('route not found', 404)
