import asyncio
from typing import List

from quart import current_app

from funding.utils import safu
from funding.models.database import Proposal, ProposalStatus, ProposalCategory, Event


class ProposalFundedTask:
    """Fetches proposal status from crypto_provider RPC, auto-moves
    to 'work-in-progress' when funding is > 100%
    """
    async def is_funded_task(self):
        while True:
            await self._is_funded()
            await asyncio.sleep(300)

    @safu
    async def _is_funded(self):
        q: List[Proposal] = Proposal.select().filter(Proposal.status == ProposalStatus.funding_required)
        for p in q:
            try:
                await p.check_funding_status()
                for event in p._events:
                    event.save(force_insert=True)
            except Exception as ex:
                current_app.logger.error(f"_is_funded task: {ex}")
