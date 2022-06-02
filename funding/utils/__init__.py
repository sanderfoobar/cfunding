import re
import hashlib
import json
import asyncio
import os
import random
from datetime import datetime
from collections import Counter
from functools import wraps
from typing import List, Union
from io import BytesIO

import settings
import aiohttp
import aiofiles
from quart import request, current_app as app, Response, url_for


def remote_address():
    if 'X-Forwarded-For' in request.headers:
        return request.headers['X-Forwarded-For']
    return request.remote_addr


def safu(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as ex:
            print(f"safu error: {ex}")
    return wrapper


def get_ip():
    if settings.X_FORWARDED:
        return request.headers.get('X-Forwarded-For')
    else:
        return request.remote_addr


def validate_crypto_address(address: str) -> bool:
    from funding.factory import coin
    addr_length = coin['address_length']

    if isinstance(addr_length, int):
        return len(address) == addr_length
    elif isinstance(addr_length, list):
        return addr_length[0] <= len(address) <= addr_length[1]
    return False
