import pytest

from tests.world import World


@pytest.fixture
def world() -> World:
    return World()
