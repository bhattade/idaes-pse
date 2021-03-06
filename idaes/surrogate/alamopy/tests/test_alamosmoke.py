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
Smoke tests, to make sure things are working at all.
"""
import pytest

def test_doalamo_import():
    from idaes.surrogate.alamopy import alamo


@pytest.mark.nocircleci()
def test_hasalamo():
    from idaes.surrogate import alamopy
    has_alamo_flag = alamopy.multos.has_alamo()
    if has_alamo_flag:
        alamopy.debug['has_alamo'] = True
        version = alamopy.get_alamo_version()
    else:
        alamopy.debug['has_alamo'] = False
        version = "n/a"  # cannot get version w/o alamo present

    print("ALAMO Version: %s"% version)

