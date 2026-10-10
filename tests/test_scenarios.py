# Every scenario in the library, played headless with its checkpoint
# expectations evaluated. Slow scenarios run only with BROADSIDE_SLOW=1.
# Same thing from the command line: python -m broadside.scenarios check

import os

import pytest

from broadside.scenarios.base import all_scenarios
from broadside.scenarios.runner import play

SCENARIOS = all_scenarios()


@pytest.mark.parametrize("scn", SCENARIOS, ids=[s.key for s in SCENARIOS])
def test_scenario(scn):
    if scn.slow and not os.environ.get("BROADSIDE_SLOW"):
        pytest.skip("slow scenario (set BROADSIDE_SLOW=1)")
    pb = play(scn, frames=False)
    failures = [f"t={r.time_s}: {r.label} [{r.detail}]" for r in pb.results if not r.ok]
    assert not failures, "\n".join(failures)
