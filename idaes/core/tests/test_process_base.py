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
Tests for process_base.

Author: Andrew Lee
"""
import pytest

from pyomo.environ import Block, ConcreteModel

from idaes.core.process_base import ProcessBaseBlock
from idaes.core import (FlowsheetBlockData,
                        declare_process_block_class)
from idaes.core.util.exceptions import ConfigurationError


@declare_process_block_class("Flowsheet")
class _Flowsheet(FlowsheetBlockData):
    def build(self):
        super(FlowsheetBlockData, self).build()


def test_flowsheet():
    # Test flowsheet method
    m = ConcreteModel()
    m.a = Flowsheet()

    assert m.a.flowsheet() is None

    m.b = Block()
    m.b.c = Flowsheet()
    assert m.b.c.flowsheet() is None

    m.a.d = Flowsheet()
    assert m.a.d.flowsheet() is m.a

    m.a.e = Flowsheet([1, 2])
    assert m.a.e[1].flowsheet() is m.a

    m.a.e[1].f = Flowsheet()
    assert m.a.e[1].f.flowsheet() is m.a.e[1]

    m.a.g = Block()
    m.a.g.h = Flowsheet()
    assert m.a.g.h.flowsheet() is m.a

    m.a.i = Block([1, 2])
    m.a.i[1].j = Flowsheet()
    assert m.a.i[1].j.flowsheet() is m.a


def test_get_performance_contents():
    m = ConcreteModel()
    m.b = ProcessBaseBlock()
    assert m.b._get_performance_contents(time_point=0) is None


def test_get_stream_table_contents():
    m = ConcreteModel()
    m.b = ProcessBaseBlock()
    assert m.b._get_stream_table_contents(time_point=0) is None


def test_report():
    # Test that no exceptions occur
    m = ConcreteModel()
    m.b = ProcessBaseBlock()
    m.b.report(dof=True)
