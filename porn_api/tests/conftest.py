import pytest_asyncio

from porn_api import Client


@pytest_asyncio.fixture
async def client():
    async with Client() as value:
        yield value
