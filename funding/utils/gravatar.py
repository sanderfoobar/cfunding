import asyncio
import os

import aiohttp
import aiofiles

GRAVATAR_LOCK = asyncio.Lock()


async def gravatar_download(hash: str, save_to_dir: str, filename: str) -> str:
    """Download image, save to disk, return abs. path"""
    dest = os.path.join(save_to_dir, filename)
    url = f'https://www.gravatar.com/avatar/{hash}'
    async with GRAVATAR_LOCK:
        timeout = aiohttp.ClientTimeout(connect=3, total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                content_type = resp.headers.get('content-type')
                if not content_type.startswith("image"):
                    raise Exception("gravatar failure")

                data: bytes = await resp.content.read()
                async with aiofiles.open(dest, mode='wb') as f:
                    await f.write(data)
        return dest
