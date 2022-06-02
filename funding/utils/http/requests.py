import aiohttp

import settings
from funding.utils.http.agents import random_agent


class Http:
    def __init__(self):
        self.opts = {
            "timeout": aiohttp.ClientTimeout(total=5)
        }

        self.headers = {
            'User-Agent': random_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }

    async def get(self, url, json_response=True, verify_tls=True):
        async with aiohttp.ClientSession(**self.opts).get(url, headers=self.headers, ssl=verify_tls) as resp:
            resp.raise_for_status()
            result = await resp.json() if json_response else await resp.text()
            if result is None or (isinstance(result, str) and result == ''):
                raise Exception("empty response from request")
            return result

    async def post(self, url, data: dict, json_response=True, verify_tls=True):
        async with aiohttp.ClientSession(**self.opts).post(url, data=data, headers=self.headers, ssl=verify_tls) as resp:
            resp.raise_for_status()
            result = await resp.json() if json_response else await resp.text()
            if result is None or (isinstance(result, str) and result == ''):
                raise Exception("empty response from request")
            return result
