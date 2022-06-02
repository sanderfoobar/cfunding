from typing import List, Optional, Tuple
import json
from datetime import datetime
import asyncio
from typing import Optional
from datetime import datetime

import aiohttp
from quart import current_app
from pydantic import BaseModel

import settings
from funding.utils import safu


class DiscourseComment(BaseModel):
    author: str
    markdown: str
    html: str
    updated_at: datetime
    created_at: datetime
    topic_id: int
    avatar_template: str

    class Config:
        use_enum_values = True

    @property
    def markdown_to_html(self):
        from funding.utils.markdown import generate_html
        return generate_html(self.markdown)

    @property
    def avatar(self):
        size = self.avatar_template.replace("{size}", "128")
        return f"https://{settings.DISCOURSE_DOMAIN}{size}"


class Discourse:
    def __init__(self):
        self._max_concurrency = 4
        self._semaphore = asyncio.Semaphore(self._max_concurrency)
        self._headers = {
            "User-Agent": "funding",
            "Api-Key": settings.DISCOURSE_API_KEY,
            "Api-Username": settings.DISCOURSE_USERNAME
        }
        self._headers_no_auth = {
            "User-Agent": self._headers['User-Agent']
        }

    async def fetch_task(self):
        while True:
            await self._fetch_task()
            await asyncio.sleep(3610)

    @safu
    async def _fetch_task(self):
        from funding.models.database import Proposal, ProposalStatus
        q: List[Proposal] = Proposal.select() \
            .filter(Proposal.status != ProposalStatus.disabled,
                    Proposal.status != ProposalStatus.completed,
                    Proposal.discourse_topic_id.is_null(False))

        cache = current_app.session_interface
        for p in q:
            try:
                res = await cache.get(p.comments_cache_key)
                if res:
                    return

                comments = await self.get_comments(p.discourse_topic_id)
                serialized = [c.json() for c in comments]

                if serialized:
                    await cache.set(p.comments_cache_key, json.dumps(serialized), expiry=3610)
            except Exception as ex:
                msg = f"discourse topic id {p.discourse_topic_id} error: {ex}"
                current_app.logger.error(msg)

    async def new_post(self, topic_id: int, body: str):
        if len(body) < 6:
            raise Exception("Post too short")

        url = f"https://{settings.DISCOURSE_DOMAIN}/posts"
        timeout = aiohttp.ClientTimeout(total=4)

        data = {
            "raw": body,
            "topic_id": topic_id
        }

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=data, headers=self._headers) as response:
                blob = await response.json()
                topic_id = blob['topic_id']
                return topic_id

    async def new_topic(self, title: str, body: str, category: int = None):
        """Returns integer (topic_id) on success, dict on error"""
        if len(body) < 40:
            raise Exception("Post too short")

        url = f"https://{settings.DISCOURSE_DOMAIN}/posts"
        timeout = aiohttp.ClientTimeout(total=4)

        data = {
            "title": title,
            "raw": body
        }

        if isinstance(category, int) and category >= 0:
            data['category'] = category

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, data=data, headers=self._headers) as response:
                blob = await response.json()
                if 'topic_id' not in blob:
                    return blob
                topic_id = blob['topic_id']
                return topic_id

    async def get_comments(self, topic_id: int) -> List[DiscourseComment]:
        post_ids = await self._posts_by_topic(topic_id)
        if not post_ids:
            return []

        # fetch last X comments
        per_topic = settings.DISCOURSE_MAX_COMMENTS_PER_TOPIC
        if per_topic >= 1:
            post_ids = post_ids[-abs(per_topic):]

        if not post_ids:
            return []

        posts = []
        for p in post_ids:
            res = await self._get_post(post_id=p)
            posts.append(res)

        return [p for p in posts if isinstance(p, DiscourseComment) and p.author != settings.DISCOURSE_USERNAME]

    @safu
    async def _posts_by_topic(self, topic_id: int):
        url = f"https://{settings.DISCOURSE_DOMAIN}/t/{topic_id}.json"
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=self._headers_no_auth) as resp:
                blob = await resp.json()
                return blob['post_stream']['stream']

    @safu
    async def _get_post(self, post_id: int) -> Optional[DiscourseComment]:
        await self._semaphore.acquire()

        url = f"https://{settings.DISCOURSE_DOMAIN}/posts/{post_id}.json"
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=self._headers_no_auth) as resp:
                blob = await resp.json()
                if 'errors' in blob:
                    current_app.logger.error(json.dumps(blob['errors']))
                    return

                result = DiscourseComment(
                    author=blob['username'],
                    markdown=blob['raw'],
                    html=blob['cooked'],
                    created_at=blob['created_at'],
                    updated_at=blob['updated_at'],
                    topic_id=blob['topic_id'],
                    avatar_template=blob['avatar_template']
                )

        self._semaphore.release()
        return result
