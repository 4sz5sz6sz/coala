from coala import Lab
import pytest


def test_all_world(tutorial_lab: Lab):
    # world load 가 문제없는지 확인함
    assert isinstance(tutorial_lab, Lab)
    assert tutorial_lab.lab_name == "tutorial_lab"


@pytest.mark.asyncio
async def test_fuse_fire_and_water(tutorial_lab: Lab):
    result = await tutorial_lab.fuse("fire", "water")
    assert result == "steam"
