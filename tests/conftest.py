from pathlib import Path
import pytest
from coala import Lab


@pytest.fixture(scope="module")
def lab(lab_name: str):
    """Session-scoped fixture to provide the lab instance."""
    lab = Lab(lab_name)
    return lab
