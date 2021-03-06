##############################################################################
# Institute for the Design of Advanced Energy Systems Process Systems
# Engineering Framework (IDAES PSE Framework) Copyright (c) 2018-2019, by the
# software owners: The Regents of the University of California, through
# Lawrence Berkeley National Laboratory,  National Technology & Engineering
# Solutions of Sandia, LLC, Carnegie Mellon University, West Virginia
# University Research Corporation, et al. All rights reserved.
#
# Please see the files COPYRIGHT.txt and LICENSE.txt for full copyright and
# license information, respectively. Both files are also available online
# at the URL "https://github.com/IDAES/idaes-pse".
##############################################################################
"""
Tests for Python code style.
"""
import logging
import os
from pathlib import Path
import subprocess

_log = logging.getLogger(__name__)


# The most stylish dirs in the project
DIRS = [
    str(p)
    for p in (
        Path("idaes/dmf"),
        # Path("apps/ddm-learning/alamo_python/alamopy"),
        # Path("apps/ddm-learning/ripe_python/ripe"),
    )
]


STYLE_CHECK_CMD = "flake8"


def test_flake8():
    cwd = os.getcwd()
    for d in DIRS:
        path = os.path.join(cwd, d)
        if not os.path.exists(path):
            _log.warning(
                f"Target path '{d}' not found in current dir, '{cwd}'. " "Skipping test"
            )
            continue
        if not os.path.isdir(path):
            _log.warning(
                f"Target path '{d}' in current dir, '{cwd}', is not a directory. "
                "Skipping test"
            )
            continue
        cmd = [STYLE_CHECK_CMD, d]
        _log.info(f"Test code style with command '{' '.join(cmd)}'")
        try:
            proc = subprocess.Popen(cmd)
        except FileNotFoundError:
            _log.warning(
                f"Style checker {STYLE_CHECK_CMD} not found. Skipping style tests"
            )
            break
        proc.wait()
        status = proc.returncode
        assert status == 0, f"Style checker '{STYLE_CHECK_CMD}' had errors for {path}"
