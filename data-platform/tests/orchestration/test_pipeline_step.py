import os
import pathlib
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "orchestration" / "pipeline_step.sh"


@pytest.mark.parametrize("cmd", ["", "bash", "extract; id", "upload && id", "../extract", "EXTRACT"])
def test_comando_nao_permitido(cmd):
    r = subprocess.run(["bash", str(SCRIPT)], env={**os.environ, "SSH_ORIGINAL_COMMAND": cmd},
                       capture_output=True, text=True)
    assert r.returncode == 2
    assert "não permitido" in r.stderr
