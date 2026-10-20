"""Alpha Vantage ingestion. Latest financial responses are not point-in-time data."""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

class AlphaVantage:
    def __init__(self):
        self.key = os.environ.get('ALPHAVANTAGE_API_KEY')
        if not self.key:
            raise ValueError('Set ALPHAVANTAGE_API_KEY in the environment')
        self.delay = 60 / max(1, int(os.getenv('ALPHAVANTAGE_REQUESTS_PER_MINUTE', '75')))
        self.last = 0

    def fetch(self, function, **params):
        time.sleep(max(0, self.delay - (time.monotonic() - self.last)))
        query = urlencode(dict(function=function, apikey=self.key, **params))
        try:
            with urlopen('https://www.alphavantage.co/query?' + query, timeout=45) as response:
                result = json.load(response)
        except Exception:
            # Never expose a request URL containing the key.
            raise RuntimeError('Market-data request failed; check connectivity and subscription') from None
        finally:
            self.last = time.monotonic()
        if any(k in result for k in ('Error Message', 'Note', 'Information')):
            raise RuntimeError('Provider rejected request or applied rate/entitlement limit')
        return result

    def snapshot(self, symbol, directory='private/data'):
        if not symbol.replace('.', '').replace('-', '').isalnum():
            raise ValueError('Invalid ticker')
        folder = Path(directory) / symbol.upper()
        folder.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
        for endpoint in ('TIME_SERIES_DAILY_ADJUSTED', 'INCOME_STATEMENT', 'BALANCE_SHEET',
                         'CASH_FLOW', 'OVERVIEW', 'EARNINGS'):
            args = {'symbol': symbol.upper()}
            if endpoint.startswith('TIME_SERIES'):
                args['outputsize'] = 'full'
            data = self.fetch(endpoint, **args)
            payload = {'retrieved_at_utc': stamp, 'historical_availability_verified': False,
                       'function': endpoint, 'data': data}
            (folder / f'{endpoint}_{stamp}.json').write_text(json.dumps(payload, indent=2))
        return str(folder)
