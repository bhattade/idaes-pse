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
Tests for Reboiler unit model. Tests 2 sets of state vars using the
ideal property package (FTPz and FcTP).

Author: Jaffer Ghouse
"""
import pytest
from pyomo.environ import (ConcreteModel, TerminationCondition,
                           SolverStatus, value)

from idaes.core import FlowsheetBlock, MaterialBalanceType, EnergyBalanceType, \
    MomentumBalanceType
from idaes.generic_models.unit_models.distillation import Reboiler
from idaes.generic_models.properties.activity_coeff_models.BTX_activity_coeff_VLE \
    import BTXParameterBlock
from idaes.core.util.model_statistics import degrees_of_freedom, \
    number_variables, number_total_constraints, number_unused_variables, \
    fixed_variables_set, activated_constraints_set
from idaes.core.util.testing import get_default_solver, \
    PhysicalParameterTestBlock

# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_default_solver()


def test_config():

    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})
    m.fs.properties = PhysicalParameterTestBlock()

    m.fs.unit = Reboiler(default={"property_package": m.fs.properties})

    assert len(m.fs.unit.config) == 9

    assert not m.fs.unit.config.has_boilup_ratio
    assert m.fs.unit.config.material_balance_type == \
        MaterialBalanceType.useDefault
    assert m.fs.unit.config.energy_balance_type == \
        EnergyBalanceType.useDefault
    assert m.fs.unit.config.momentum_balance_type == \
        MomentumBalanceType.pressureTotal
    assert not m.fs.unit.config.has_pressure_change
    assert hasattr(m.fs.unit, "heat_duty")


class TestBTXIdeal(object):
    @pytest.fixture(scope="class")
    def btx_ftpz(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = BTXParameterBlock(default={"valid_phase":
                                                     ('Liq', 'Vap'),
                                                     "activity_coeff_model":
                                                     "Ideal"})

        m.fs.unit = Reboiler(
            default={"property_package": m.fs.properties,
                     "has_boilup_ratio": True,
                     "has_pressure_change": True})

        return m

    @pytest.fixture(scope="class")
    def btx_fctp(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = BTXParameterBlock(default={"valid_phase":
                                                     ('Liq', 'Vap'),
                                                     "activity_coeff_model":
                                                     "Ideal",
                                                     "state_vars": "FcTP"})

        m.fs.unit = Reboiler(
            default={"property_package": m.fs.properties,
                     "has_boilup_ratio": True,
                     "has_pressure_change": True})

        return m

    @pytest.mark.build
    def test_build(self, btx_ftpz, btx_fctp):

        assert hasattr(btx_ftpz.fs.unit, "boilup_ratio")
        assert hasattr(btx_ftpz.fs.unit, "eq_boilup_ratio")

        assert hasattr(btx_ftpz.fs.unit, "inlet")
        assert hasattr(btx_ftpz.fs.unit.inlet, "flow_mol")
        assert hasattr(btx_ftpz.fs.unit.inlet, "mole_frac_comp")
        assert hasattr(btx_ftpz.fs.unit.inlet, "temperature")
        assert hasattr(btx_ftpz.fs.unit.inlet, "pressure")

        assert hasattr(btx_ftpz.fs.unit, "bottoms")
        assert hasattr(btx_ftpz.fs.unit.bottoms, "flow_mol")
        assert hasattr(btx_ftpz.fs.unit.bottoms, "mole_frac_comp")
        assert hasattr(btx_ftpz.fs.unit.bottoms, "temperature")
        assert hasattr(btx_ftpz.fs.unit.bottoms, "pressure")

        assert hasattr(btx_ftpz.fs.unit, "vapor_reboil")
        assert hasattr(btx_ftpz.fs.unit.vapor_reboil, "flow_mol")
        assert hasattr(btx_ftpz.fs.unit.vapor_reboil, "mole_frac_comp")
        assert hasattr(btx_ftpz.fs.unit.vapor_reboil, "temperature")
        assert hasattr(btx_ftpz.fs.unit.vapor_reboil, "pressure")

        assert number_variables(btx_ftpz.fs.unit) == 49
        assert number_total_constraints(btx_ftpz.fs.unit) == 42
        assert number_unused_variables(btx_ftpz) == 0

        assert hasattr(btx_fctp.fs.unit, "boilup_ratio")
        assert hasattr(btx_fctp.fs.unit, "eq_boilup_ratio")

        assert hasattr(btx_fctp.fs.unit, "inlet")
        assert hasattr(btx_fctp.fs.unit.inlet, "flow_mol_comp")
        assert hasattr(btx_fctp.fs.unit.inlet, "temperature")
        assert hasattr(btx_fctp.fs.unit.inlet, "pressure")

        assert hasattr(btx_fctp.fs.unit, "bottoms")
        assert hasattr(btx_fctp.fs.unit.bottoms, "flow_mol_comp")
        assert hasattr(btx_fctp.fs.unit.bottoms, "temperature")
        assert hasattr(btx_fctp.fs.unit.bottoms, "pressure")

        assert hasattr(btx_fctp.fs.unit, "vapor_reboil")
        assert hasattr(btx_fctp.fs.unit.vapor_reboil, "flow_mol_comp")
        assert hasattr(btx_fctp.fs.unit.vapor_reboil, "temperature")
        assert hasattr(btx_fctp.fs.unit.vapor_reboil, "pressure")

        assert number_variables(btx_fctp.fs.unit) == 51
        assert number_total_constraints(btx_fctp.fs.unit) == 45
        assert number_unused_variables(btx_fctp) == 0

    def test_dof(self, btx_ftpz, btx_fctp):

        # Fix the reboiler variables
        btx_ftpz.fs.unit.boilup_ratio.fix(1)
        btx_ftpz.fs.unit.deltaP.fix(0)

        # Fix the inputs (typically this will be the outlet liquid from the
        # bottom tray)
        btx_ftpz.fs.unit.inlet.flow_mol.fix(1)
        btx_ftpz.fs.unit.inlet.temperature.fix(363)
        btx_ftpz.fs.unit.inlet.pressure.fix(101325)
        btx_ftpz.fs.unit.inlet.mole_frac_comp[0, "benzene"].fix(0.5)
        btx_ftpz.fs.unit.inlet.mole_frac_comp[0, "toluene"].fix(0.5)

        assert degrees_of_freedom(btx_ftpz) == 0

        # Fix the reboiler variables
        btx_fctp.fs.unit.boilup_ratio.fix(1)
        btx_fctp.fs.unit.deltaP.fix(0)

        # Fix the inputs (typically this will be the outlet liquid from the
        # bottom tray)
        btx_fctp.fs.unit.inlet.flow_mol_comp[0, "benzene"].fix(0.5)
        btx_fctp.fs.unit.inlet.flow_mol_comp[0, "toluene"].fix(0.5)
        btx_fctp.fs.unit.inlet.temperature.fix(363)
        btx_fctp.fs.unit.inlet.pressure.fix(101325)

        assert degrees_of_freedom(btx_fctp) == 0

    @pytest.mark.initialization
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize(self, btx_ftpz, btx_fctp):
        orig_fixed_vars = fixed_variables_set(btx_ftpz)
        orig_act_consts = activated_constraints_set(btx_ftpz)

        btx_ftpz.fs.unit.initialize(solver=solver)

        assert degrees_of_freedom(btx_ftpz) == 0

        fin_fixed_vars = fixed_variables_set(btx_ftpz)
        fin_act_consts = activated_constraints_set(btx_ftpz)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

        orig_fixed_vars = fixed_variables_set(btx_fctp)
        orig_act_consts = activated_constraints_set(btx_fctp)

        btx_fctp.fs.unit.initialize(solver=solver)

        assert degrees_of_freedom(btx_fctp) == 0

        fin_fixed_vars = fixed_variables_set(btx_fctp)
        fin_act_consts = activated_constraints_set(btx_fctp)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve(self, btx_ftpz, btx_fctp):
        results = solver.solve(btx_ftpz)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

        results = solver.solve(btx_fctp)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution(self, btx_ftpz, btx_fctp):
        # Bottoms port
        assert (pytest.approx(0.5, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.flow_mol[0]))
        assert (pytest.approx(0.3891, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.mole_frac_comp[0, "benzene"]))
        assert (pytest.approx(0.6109, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.mole_frac_comp[0, "toluene"]))
        assert (pytest.approx(368.728, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.temperature[0]))
        assert (pytest.approx(101325, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.pressure[0]))

        # Vapor reboil port
        assert (pytest.approx(0.5, abs=1e-3) ==
                value(btx_ftpz.fs.unit.vapor_reboil.flow_mol[0]))
        assert (pytest.approx(0.6108, abs=1e-3) ==
                value(btx_ftpz.fs.unit.vapor_reboil.mole_frac_comp[0, "benzene"]))
        assert (pytest.approx(0.3892, abs=1e-3) ==
                value(btx_ftpz.fs.unit.vapor_reboil.mole_frac_comp[0, "toluene"]))
        assert (pytest.approx(368.728, abs=1e-3) ==
                value(btx_ftpz.fs.unit.vapor_reboil.temperature[0]))
        assert (pytest.approx(101325, abs=1e-3) ==
                value(btx_ftpz.fs.unit.bottoms.pressure[0]))

        # Unit level
        assert (pytest.approx(16926.526, abs=1e-3) ==
                value(btx_ftpz.fs.unit.heat_duty[0]))

        # Reboiler when using FcTP

        # Bottoms port
        assert (pytest.approx(0.19455, abs=1e-3) ==
                value(btx_fctp.fs.unit.bottoms.flow_mol_comp[0, "benzene"]))
        assert (pytest.approx(0.30545, abs=1e-3) ==
                value(btx_fctp.fs.unit.bottoms.flow_mol_comp[0, "toluene"]))
        assert (pytest.approx(368.728, abs=1e-3) ==
                value(btx_fctp.fs.unit.bottoms.temperature[0]))
        assert (pytest.approx(101325, abs=1e-3) ==
                value(btx_fctp.fs.unit.bottoms.pressure[0]))

        # Vapor reboil port
        assert (pytest.approx(0.3054, abs=1e-3) ==
                value(btx_fctp.fs.unit.vapor_reboil.flow_mol_comp[0, "benzene"]))
        assert (pytest.approx(0.1946, abs=1e-3) ==
                value(btx_fctp.fs.unit.vapor_reboil.flow_mol_comp[0, "toluene"]))
        assert (pytest.approx(368.728, abs=1e-3) ==
                value(btx_fctp.fs.unit.vapor_reboil.temperature[0]))
        assert (pytest.approx(101325, abs=1e-3) ==
                value(btx_fctp.fs.unit.bottoms.pressure[0]))

        # Unit level
        assert (pytest.approx(16926.370, abs=1e-3) ==
                value(btx_fctp.fs.unit.heat_duty[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, btx_ftpz, btx_fctp):
        assert abs(value(btx_ftpz.fs.unit.inlet.flow_mol[0] -
                         (btx_ftpz.fs.unit.bottoms.flow_mol[0] +
                          btx_ftpz.fs.unit.vapor_reboil.flow_mol[0]))) <= 1e-6

        assert abs(value(btx_fctp.fs.unit.inlet.flow_mol_comp[0, "benzene"] +
                         btx_fctp.fs.unit.inlet.flow_mol_comp[0, "toluene"] -
                         (btx_fctp.fs.unit.bottoms.flow_mol_comp[0, "benzene"] +
                          btx_fctp.fs.unit.bottoms.flow_mol_comp[0, "toluene"] +
                          btx_fctp.fs.unit.vapor_reboil.
                          flow_mol_comp[0, "benzene"] +
                          btx_fctp.fs.unit.vapor_reboil.
                          flow_mol_comp[0, "toluene"]))) <= 1e-6

    @pytest.mark.ui
    def test_report(self, btx_ftpz, btx_fctp):
        btx_ftpz.fs.unit.report()
        btx_fctp.fs.unit.report()
