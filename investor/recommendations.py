"""Evidence gate: absent or unverified evidence never becomes a trade approval."""
import math
from datetime import datetime, timezone

EVIDENCE = ('revenue_growth_yoy', 'guidance_change', 'profitability_cash_debt',
            'valuation', 'market_sector_trend', 'cpi_rate_sensitivity',
            'price_performance', 'catalysts_risks', 'broker_costs_availability')

def utc(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Timezone required')
    return result.astimezone(timezone.utc)

def blockers(card, now=None):
    now = now or datetime.now(timezone.utc)
    errors = []
    if card.get('sample', False):
        errors.append('Illustrative sample; not an investment recommendation')
    if card.get('action') not in ('BUY', 'SHORT', 'CLOSE_LONG', 'COVER_SHORT'):
        errors.append('No actionable trade')
    try:
        if not utc(card['created_at']) <= now < utc(card['expires_at']):
            errors.append('Recommendation expired or not yet valid')
        if not 0 <= (now - utc(card['quote_at'])).total_seconds() <= 900:
            errors.append('Price is older than 15 minutes or in the future')
    except (KeyError, ValueError, TypeError):
        errors.append('Missing or invalid timestamps')
    evidence = card.get('evidence', {})
    for name in EVIDENCE:
        item = evidence.get(name, {})
        if not item.get('verified') or not item.get('summary') or not item.get('source'):
            errors.append('Unverified evidence: ' + name)
        try:
            if utc(item['published_at']) > now:
                errors.append('Future evidence: ' + name)
        except (KeyError, ValueError, TypeError):
            errors.append('Missing evidence publication time: ' + name)
    try:
        entry, stop, target, units = [float(card[k]) for k in ('entry', 'stop', 'target', 'units')]
        if not all(math.isfinite(x) and x > 0 for x in (entry, stop, target, units)):
            raise ValueError()
        if card['action'] == 'BUY' and not stop < entry < target:
            errors.append('Invalid long levels')
        if card['action'] == 'SHORT' and not target < entry < stop:
            errors.append('Invalid short levels')
        if card['action'] in ('BUY', 'SHORT'):
            if abs(entry-stop)*units > 50:
                errors.append('Planned stop risk exceeds initial $50 limit')
            if entry*units > 1500:
                errors.append('Position exceeds initial $1,500 notional limit')
    except (KeyError, ValueError, TypeError):
        errors.append('Invalid trade sizing')
    if not card.get('broker_verified'):
        errors.append('Broker instrument and costs not verified')
    return errors
