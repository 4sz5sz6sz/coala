from asyncio import sleep
from pathlib import Path

import pytest_asyncio
from coala import Lab


@pytest_asyncio.fixture(scope="module")
async def lab(lab_name: str, pytestconfig):
    """Session-scoped async fixture to provide the tutorial_lab instance."""

    # Try to get storage_path from cache; create it if not found
    cache_key = f"coala/{lab_name}/storage_path"
    storage_path = pytestconfig.cache.get(cache_key, None)

    if storage_path is None:
        # Use pytest's cache directory to store InfiniteCraft discoveries
        cache_dir = pytestconfig.cache.mkdir("coala_discoveries")
        storage_path = str(cache_dir / f"{lab_name}.json")
        pytestconfig.cache.set(cache_key, storage_path)

    lab = Lab(lab_name, storage_path)
    await lab.start()
    yield lab
    # lab 호출 간 callee 를 놀래키지 않도록 sleep 추가
    await sleep(0.5)
    await lab.close()
