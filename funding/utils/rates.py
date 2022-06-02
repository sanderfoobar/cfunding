import asyncio
import json

import aiohttp
from quart import current_app

import settings
from funding.utils.http.agents import random_agent
from funding.utils import safu


class Rates:
    def __init__(self):
        self.rate: float = 0.0

    async def rate_task(self):
        while True:
            if await self._rate_task():
                current_app.logger.info("Fetched USD rate")
            else:
                current_app.logger.error("Failed to fetch USD rate; retrying in 10 minutes")
            await asyncio.sleep(600)

    async def to_usd(self, amount: float):
        if self.rate == 0:
            return 0
        return round(self.rate * amount, 2)

    @safu
    async def _rate_task(self):
        from funding.factory import coin

        cgid = coin['coingecko_id']
        cache_key = f"usd_rate_{cgid}"

        cache = current_app.session_interface
        result = await cache.get(cache_key)
        if result:
            result = json.loads(result)
            self.rate = result

        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cgid}&vs_currencies=usd"
        ua = random_agent()
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(headers={"User-Agent": ua}, timeout=timeout) as session:
            async with session.get(url) as resp:
                data = await resp.json()
                try:
                    self.rate = data[cgid]['usd']
                    return self.rate
                except Exception as ex:
                    data = json.dumps(data)
                    current_app.logger.error(f"Could not parse JSON response; {data}")
