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
Tests for ControlVolumeBlockData.

Author: Andrew Lee
"""
import pytest

from pyomo.environ import (ConcreteModel,
                           TerminationCondition,
                           SolverStatus,
                           value)

from idaes.core import FlowsheetBlock, EnergyBalanceType, MomentumBalanceType
from idaes.generic_models.unit_models.gibbs_reactor import GibbsReactor
from idaes.generic_models.properties.activity_coeff_models.methane_combustion_ideal \
    import MethaneParameterBlock as MethaneCombustionParameterBlock
from idaes.core.util.model_statistics import (degrees_of_freedom,
                                              number_variables,
                                              number_total_constraints,
                                              fixed_variables_set,
                                              activated_constraints_set,
                                              number_unused_variables)
from idaes.core.util.testing import (get_default_solver,
                                     PhysicalParameterTestBlock)


# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_default_solver()


# -----------------------------------------------------------------------------
def test_config():
    m = ConcreteModel()
    m.fs = FlowsheetBlock(default={"dynamic": False})

    m.fs.properties = PhysicalParameterTestBlock()

    m.fs.unit = GibbsReactor(default={"property_package": m.fs.properties})

    # Check unit config arguments
    assert len(m.fs.unit.config) == 8

    assert not m.fs.unit.config.dynamic
    assert not m.fs.unit.config.has_holdup
    assert m.fs.unit.config.energy_balance_type == \
        EnergyBalanceType.useDefault
    assert m.fs.unit.config.momentum_balance_type == \
        MomentumBalanceType.pressureTotal
    assert not m.fs.unit.config.has_heat_transfer
    assert not m.fs.unit.config.has_pressure_change
    assert m.fs.unit.config.property_package is m.fs.properties


# -----------------------------------------------------------------------------
class TestSaponification(object):
    @pytest.fixture(scope="class")
    def methane(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = MethaneCombustionParameterBlock()

        m.fs.unit = GibbsReactor(default={
                "property_package": m.fs.properties,
                "has_heat_transfer": True,
                "has_pressure_change": True})

        return m

    @pytest.mark.build
    def test_build(self, methane):
        assert hasattr(methane.fs.unit, "inlet")
        assert len(methane.fs.unit.inlet.vars) == 4
        assert hasattr(methane.fs.unit.inlet, "flow_mol")
        assert hasattr(methane.fs.unit.inlet, "mole_frac_comp")
        assert hasattr(methane.fs.unit.inlet, "temperature")
        assert hasattr(methane.fs.unit.inlet, "pressure")

        assert hasattr(methane.fs.unit, "outlet")
        assert len(methane.fs.unit.outlet.vars) == 4
        assert hasattr(methane.fs.unit.outlet, "flow_mol")
        assert hasattr(methane.fs.unit.outlet, "mole_frac_comp")
        assert hasattr(methane.fs.unit.outlet, "temperature")
        assert hasattr(methane.fs.unit.outlet, "pressure")

        assert hasattr(methane.fs.unit, "gibbs_minimization")
        assert hasattr(methane.fs.unit, "heat_duty")
        assert hasattr(methane.fs.unit, "deltaP")

        assert number_variables(methane) == 80
        assert number_total_constraints(methane) == 67
        assert number_unused_variables(methane) == 0

    def test_dof(self, methane):
        methane.fs.unit.inlet.flow_mol[0].fix(230.0)
        methane.fs.unit.inlet.mole_frac_comp[0, "H2"].fix(0.0435)
        methane.fs.unit.inlet.mole_frac_comp[0, "N2"].fix(0.6522)
        methane.fs.unit.inlet.mole_frac_comp[0, "O2"].fix(0.1739)
        methane.fs.unit.inlet.mole_frac_comp[0, "CO2"].fix(1e-5)
        methane.fs.unit.inlet.mole_frac_comp[0, "CH4"].fix(0.1304)
        methane.fs.unit.inlet.mole_frac_comp[0, "CO"].fix(1e-5)
        methane.fs.unit.inlet.mole_frac_comp[0, "H2O"].fix(1e-5)
        methane.fs.unit.inlet.mole_frac_comp[0, "NH3"].fix(1e-5)
        methane.fs.unit.inlet.temperature[0].fix(1500.0)
        methane.fs.unit.inlet.pressure[0].fix(101325.0)

        methane.fs.unit.outlet.temperature[0].fix(2844.38)
        methane.fs.unit.deltaP.fix(0)

        assert degrees_of_freedom(methane) == 0

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize_temperature(self, methane):
        orig_fixed_vars = fixed_variables_set(methane)
        orig_act_consts = activated_constraints_set(methane)

        methane.fs.unit.initialize(
                          optarg={'tol': 1e-6},
                          state_args={'temperature': 2844.38,
                                      'pressure': 101325.0,
                                      'flow_mol': 251.05,
                                      'mole_frac_comp': {'CH4': 1e-5,
                                                         'CO': 0.0916,
                                                         'CO2': 0.0281,
                                                         'H2': 0.1155,
                                                         'H2O': 0.1633,
                                                         'N2': 0.5975,
                                                         'NH3': 1e-5,
                                                         'O2': 0.0067}})

        assert degrees_of_freedom(methane) == 0

        fin_fixed_vars = fixed_variables_set(methane)
        fin_act_consts = activated_constraints_set(methane)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve_temperature(self, methane):
        results = solver.solve(methane)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution_temperature(self, methane):
        assert (pytest.approx(250.06, abs=1e-2) ==
                value(methane.fs.unit.outlet.flow_mol[0]))
        assert (pytest.approx(0.0, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CH4"]))
        assert (pytest.approx(0.0974, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CO"]))
        assert (pytest.approx(0.0226, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CO2"]))
        assert (pytest.approx(0.1030, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "H2"]))
        assert (pytest.approx(0.1769, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "H2O"]))
        assert (pytest.approx(0.5999, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "N2"]))
        assert (pytest.approx(0.0, abs=1e-5) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "NH3"]))
        assert (pytest.approx(0.0002, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "O2"]))
        assert (pytest.approx(-7454077, abs=1e2) ==
                value(methane.fs.unit.heat_duty[0]))
        assert (pytest.approx(101325.0, abs=1e-2) ==
                value(methane.fs.unit.outlet.pressure[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation_temperature(self, methane):
        assert abs(value(
                methane.fs.unit.inlet.flow_mol[0] *
                methane.fs.unit.control_volume.properties_in[0]
                    .enth_mol_phase["Vap"] -
                methane.fs.unit.outlet.flow_mol[0] *
                methane.fs.unit.control_volume.properties_out[0]
                    .enth_mol_phase["Vap"] +
                methane.fs.unit.heat_duty[0])) <= 1e-6

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize_duty(self, methane):
        methane.fs.unit.outlet.temperature[0].unfix()
        methane.fs.unit.heat_duty.fix(-7454077)
        assert degrees_of_freedom(methane) == 0

        orig_fixed_vars = fixed_variables_set(methane)
        orig_act_consts = activated_constraints_set(methane)

        methane.fs.unit.initialize(
                          optarg={'tol': 1e-6},
                          state_args={'temperature': 2844.38,
                                      'pressure': 101325.0,
                                      'flow_mol': 251.05,
                                      'mole_frac_comp': {'CH4': 1e-5,
                                                         'CO': 0.0916,
                                                         'CO2': 0.0281,
                                                         'H2': 0.1155,
                                                         'H2O': 0.1633,
                                                         'N2': 0.5975,
                                                         'NH3': 1e-5,
                                                         'O2': 0.0067}})

        assert degrees_of_freedom(methane) == 0

        fin_fixed_vars = fixed_variables_set(methane)
        fin_act_consts = activated_constraints_set(methane)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve_heat_duty(self, methane):
        results = solver.solve(methane)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution_duty(self, methane):
        assert (pytest.approx(250.06, abs=1e-2) ==
                value(methane.fs.unit.outlet.flow_mol[0]))
        assert (pytest.approx(0.0, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CH4"]))
        assert (pytest.approx(0.0974, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CO"]))
        assert (pytest.approx(0.0226, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "CO2"]))
        assert (pytest.approx(0.1030, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "H2"]))
        assert (pytest.approx(0.1769, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "H2O"]))
        assert (pytest.approx(0.5999, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "N2"]))
        assert (pytest.approx(0.0, abs=1e-5) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "NH3"]))
        assert (pytest.approx(0.0002, abs=1e-4) ==
                value(methane.fs.unit.outlet.mole_frac_comp[0, "O2"]))
        assert (pytest.approx(-7454077, abs=1e2) ==
                value(methane.fs.unit.heat_duty[0]))
        assert (pytest.approx(101325.0, abs=1e-2) ==
                value(methane.fs.unit.outlet.pressure[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation_duty(self, methane):
        assert abs(value(
                methane.fs.unit.inlet.flow_mol[0] *
                methane.fs.unit.control_volume.properties_in[0]
                    .enth_mol_phase["Vap"] -
                methane.fs.unit.outlet.flow_mol[0] *
                methane.fs.unit.control_volume.properties_out[0]
                    .enth_mol_phase["Vap"] +
                methane.fs.unit.heat_duty[0])) <= 1e-6

    @pytest.mark.ui
    def test_report(self, methane):
        methane.fs.unit.report()
