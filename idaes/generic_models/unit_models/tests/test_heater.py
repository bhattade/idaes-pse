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
Tests for 0D heat exchanger models.

Author: John Eslick
"""
import pytest

from pyomo.environ import (ConcreteModel,
                           SolverStatus,
                           TerminationCondition,
                           value)

from idaes.core import (FlowsheetBlock,
                        MaterialBalanceType,
                        EnergyBalanceType,
                        MomentumBalanceType)
from idaes.generic_models.unit_models import Heater

from idaes.generic_models.properties.activity_coeff_models.BTX_activity_coeff_VLE \
    import BTXParameterBlock
from idaes.generic_models.properties import iapws95
from idaes.generic_models.properties.examples.saponification_thermo import \
    SaponificationParameterBlock

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

    m.fs.unit = Heater(default={"property_package": m.fs.properties})

    # Check unit config arguments
    assert len(m.fs.unit.config) == 9
    assert not m.fs.unit.config.dynamic
    assert not m.fs.unit.config.has_holdup
    assert m.fs.unit.config.material_balance_type == \
        MaterialBalanceType.useDefault
    assert m.fs.unit.config.energy_balance_type == \
        EnergyBalanceType.useDefault
    assert m.fs.unit.config.momentum_balance_type == \
        MomentumBalanceType.pressureTotal
    assert not m.fs.unit.config.has_phase_equilibrium
    assert not m.fs.unit.config.has_pressure_change
    assert m.fs.unit.config.property_package is m.fs.properties


# -----------------------------------------------------------------------------
class TestBTX(object):
    @pytest.fixture(scope="class")
    def btx(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = BTXParameterBlock(default={"valid_phase": 'Liq'})

        m.fs.unit = Heater(default={"property_package": m.fs.properties,
                                    "has_pressure_change": True})

        return m

    @pytest.mark.build
    def test_build(self, btx):
        assert hasattr(btx.fs.unit, "inlet")
        assert len(btx.fs.unit.inlet.vars) == 4
        assert hasattr(btx.fs.unit.inlet, "flow_mol")
        assert hasattr(btx.fs.unit.inlet, "mole_frac_comp")
        assert hasattr(btx.fs.unit.inlet, "temperature")
        assert hasattr(btx.fs.unit.inlet, "pressure")

        assert hasattr(btx.fs.unit, "outlet")
        assert len(btx.fs.unit.outlet.vars) == 4
        assert hasattr(btx.fs.unit.outlet, "flow_mol")
        assert hasattr(btx.fs.unit.outlet, "mole_frac_comp")
        assert hasattr(btx.fs.unit.outlet, "temperature")
        assert hasattr(btx.fs.unit.outlet, "pressure")

        assert hasattr(btx.fs.unit, "heat_duty")
        assert hasattr(btx.fs.unit, "deltaP")

        assert number_variables(btx) == 24
        assert number_total_constraints(btx) == 17
        assert number_unused_variables(btx) == 0

    def test_dof(self, btx):
        btx.fs.unit.inlet.flow_mol[0].fix(5)  # mol/s
        btx.fs.unit.inlet.temperature[0].fix(365)  # K
        btx.fs.unit.inlet.pressure[0].fix(101325)  # Pa
        btx.fs.unit.inlet.mole_frac_comp[0, "benzene"].fix(0.5)
        btx.fs.unit.inlet.mole_frac_comp[0, "toluene"].fix(0.5)

        btx.fs.unit.heat_duty.fix(-5000)
        btx.fs.unit.deltaP.fix(0)

        assert degrees_of_freedom(btx) == 0

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize(self, btx):
        orig_fixed_vars = fixed_variables_set(btx)
        orig_act_consts = activated_constraints_set(btx)

        btx.fs.unit.initialize(optarg={'tol': 1e-6})

        assert degrees_of_freedom(btx) == 0

        fin_fixed_vars = fixed_variables_set(btx)
        fin_act_consts = activated_constraints_set(btx)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve(self, btx):
        results = solver.solve(btx)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution(self, btx):
        assert (pytest.approx(5, abs=1e-3) ==
                value(btx.fs.unit.outlet.flow_mol[0]))
        assert (pytest.approx(358.9, abs=1e-1) ==
                value(btx.fs.unit.outlet.temperature[0]))
        assert (pytest.approx(101325, abs=1e-3) ==
                value(btx.fs.unit.outlet.pressure[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, btx):
        assert abs(value(btx.fs.unit.inlet.flow_mol[0] -
                         btx.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert abs(value(
            btx.fs.unit.inlet.flow_mol[0] *
            btx.fs.unit.control_volume.properties_in[0].enth_mol_phase["Liq"] -
            btx.fs.unit.outlet.flow_mol[0] *
            btx.fs.unit.control_volume.properties_out[0].enth_mol_phase["Liq"])
            + btx.fs.unit.heat_duty[0]) <= 1e-6

    @pytest.mark.ui
    def test_report(self, btx):
        btx.fs.unit.report()


# -----------------------------------------------------------------------------
@pytest.mark.iapws
@pytest.mark.skipif(not iapws95.iapws95_available(),
                    reason="IAPWS not available")
class TestIAPWS(object):
    @pytest.fixture(scope="class")
    def iapws(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = iapws95.Iapws95ParameterBlock()

        m.fs.unit = Heater(
            default={
                "property_package": m.fs.properties,
                "has_pressure_change": True
            }
        )
        m.fs.unit.deltaP.fix(0)
        return m

    @pytest.mark.build
    def test_build(self, iapws):
        assert len(iapws.fs.unit.inlet.vars) == 3
        assert hasattr(iapws.fs.unit.inlet, "flow_mol")
        assert hasattr(iapws.fs.unit.inlet, "enth_mol")
        assert hasattr(iapws.fs.unit.inlet, "pressure")

        assert hasattr(iapws.fs.unit, "outlet")
        assert len(iapws.fs.unit.outlet.vars) == 3
        assert hasattr(iapws.fs.unit.outlet, "flow_mol")
        assert hasattr(iapws.fs.unit.outlet, "enth_mol")
        assert hasattr(iapws.fs.unit.outlet, "pressure")

        assert hasattr(iapws.fs.unit, "heat_duty")

        assert number_variables(iapws) == 8
        assert number_total_constraints(iapws) == 3
        assert number_unused_variables(iapws) == 0

    def test_dof(self, iapws):
        iapws.fs.unit.inlet.flow_mol[0].fix(5)
        iapws.fs.unit.inlet.enth_mol[0].fix(50000)
        iapws.fs.unit.inlet.pressure[0].fix(101325)

        iapws.fs.unit.heat_duty.fix(10000)

        assert degrees_of_freedom(iapws) == 0

    @pytest.mark.initialization
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize(self, iapws):
        orig_fixed_vars = fixed_variables_set(iapws)
        orig_act_consts = activated_constraints_set(iapws)

        iapws.fs.unit.initialize(optarg={'tol': 1e-6})

        assert degrees_of_freedom(iapws) == 0

        fin_fixed_vars = fixed_variables_set(iapws)
        fin_act_consts = activated_constraints_set(iapws)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve(self, iapws):
        results = solver.solve(iapws)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution(self, iapws):
        assert pytest.approx(5, abs=1e-5) == \
            value(iapws.fs.unit.outlet.flow_mol[0])

        assert pytest.approx(52000, abs=1e0) == \
            value(iapws.fs.unit.outlet.enth_mol[0])

        assert pytest.approx(101325, abs=1e2) == \
            value(iapws.fs.unit.outlet.pressure[0])

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, iapws):
        assert abs(value(iapws.fs.unit.inlet.flow_mol[0] -
                         iapws.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert abs(value(
            iapws.fs.unit.inlet.flow_mol[0]*iapws.fs.unit.inlet.enth_mol[0] -
            iapws.fs.unit.outlet.flow_mol[0]*iapws.fs.unit.outlet.enth_mol[0] +
            iapws.fs.unit.heat_duty[0])) <= 1e-6

    @pytest.mark.ui
    def test_report(self, iapws):
        iapws.fs.unit.report()

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_verify(self, iapws):
        # Test the heater model against known test cases
        # Test cases from Aspen Plus 10 with iapws-95
        cases = {
            "F": (1000, 1000, 1000, 1000), # mol/s
            "Tin": (300, 300, 300, 800), # K
            "Pin": (1000, 1000, 1000, 1000), # kPa
            "xin": (0, 0, 0, 1), # vapor fraction
            "Tout": (400, 400, 453.028, 300), # K
            "Pout": (1000, 100, 1000, 1000), # kPa
            "xout": (0, 1, 0.228898, 0), # vapor fraction
            "duty": (7566.19, 47145, 20000, -61684.4), # kW
        }

        for i in [0, 1, 2, 3]:
            F = cases["F"][i]
            Tin = cases["Tin"][i]
            Pin = cases["Pin"][i]*1000
            xin = cases["xin"][i]
            hin = iapws95.htpx(T=Tin, P=Pin)
            Tout = cases["Tout"][i]
            Pout = cases["Pout"][i]*1000
            xout = cases["xout"][i]
            duty = cases["duty"][i]*1000
            if xout != 0 and xout != 1:
                hout = iapws95.htpx(T=Tout, x=xout)
            else:
                hout = iapws95.htpx(T=Tout, P=Pout)
            prop_in = iapws.fs.unit.control_volume.properties_in[0]
            prop_out = iapws.fs.unit.control_volume.properties_out[0]

            prop_in.flow_mol = F
            prop_in.enth_mol = hin
            prop_in.pressure = Pin
            iapws.fs.unit.deltaP[0] = Pout - Pin
            iapws.fs.unit.heat_duty[0] = duty
            results = solver.solve(iapws)

            # Check for optimal solution
            assert results.solver.termination_condition == \
                TerminationCondition.optimal
            assert results.solver.status == SolverStatus.ok

            assert Tin == pytest.approx(value(prop_in.temperature), rel=1e-3)
            assert Tout == pytest.approx(value(prop_out.temperature), rel=1e-3)
            assert Pout == pytest.approx(value(prop_out.pressure), rel=1e-3)
            assert xout == pytest.approx(value(prop_out.vapor_frac), rel=1e-3)




# -----------------------------------------------------------------------------
class TestSaponification(object):
    @pytest.fixture(scope="class")
    def sapon(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = SaponificationParameterBlock()

        m.fs.unit = Heater(default={"property_package": m.fs.properties})

        return m

    @pytest.mark.build
    def test_build(self, sapon):
        assert len(sapon.fs.unit.inlet.vars) == 4
        assert hasattr(sapon.fs.unit.inlet, "flow_vol")
        assert hasattr(sapon.fs.unit.inlet, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.inlet, "temperature")
        assert hasattr(sapon.fs.unit.inlet, "pressure")

        assert len(sapon.fs.unit.outlet.vars) == 4
        assert hasattr(sapon.fs.unit.outlet, "flow_vol")
        assert hasattr(sapon.fs.unit.outlet, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.outlet, "temperature")
        assert hasattr(sapon.fs.unit.outlet, "pressure")

        assert hasattr(sapon.fs.unit, "heat_duty")

        assert number_variables(sapon) == 17
        assert number_total_constraints(sapon) == 8
        assert number_unused_variables(sapon) == 0

    def test_dof(self, sapon):
        sapon.fs.unit.inlet.flow_vol[0].fix(1e-3)
        sapon.fs.unit.inlet.temperature[0].fix(320)
        sapon.fs.unit.inlet.pressure[0].fix(101325)
        sapon.fs.unit.inlet.conc_mol_comp[0, "H2O"].fix(55388.0)
        sapon.fs.unit.inlet.conc_mol_comp[0, "NaOH"].fix(100.0)
        sapon.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"].fix(100.0)
        sapon.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"].fix(0.0)
        sapon.fs.unit.inlet.conc_mol_comp[0, "Ethanol"].fix(0.0)

        sapon.fs.unit.heat_duty.fix(1000)

        assert degrees_of_freedom(sapon) == 0

    @pytest.mark.initialization
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_initialize(self, sapon):
        orig_fixed_vars = fixed_variables_set(sapon)
        orig_act_consts = activated_constraints_set(sapon)

        sapon.fs.unit.initialize(optarg={'tol': 1e-6})

        assert degrees_of_freedom(sapon) == 0

        fin_fixed_vars = fixed_variables_set(sapon)
        fin_act_consts = activated_constraints_set(sapon)

        assert len(fin_act_consts) == len(orig_act_consts)
        assert len(fin_fixed_vars) == len(orig_fixed_vars)

        for c in fin_act_consts:
            assert c in orig_act_consts
        for v in fin_fixed_vars:
            assert v in orig_fixed_vars

    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solve(self, sapon):
        results = solver.solve(sapon)

        # Check for optimal solution
        assert results.solver.termination_condition == \
            TerminationCondition.optimal
        assert results.solver.status == SolverStatus.ok

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_solution(self, sapon):
        assert pytest.approx(1e-3, abs=1e-6) == \
            value(sapon.fs.unit.outlet.flow_vol[0])

        assert 55388.0 == value(
                sapon.fs.unit.inlet.conc_mol_comp[0, "H2O"])
        assert 100.0 == value(
                sapon.fs.unit.inlet.conc_mol_comp[0, "NaOH"])
        assert 100.0 == value(
                sapon.fs.unit.inlet.conc_mol_comp[0, "EthylAcetate"])
        assert 0.0 == value(
                sapon.fs.unit.inlet.conc_mol_comp[0, "SodiumAcetate"])
        assert 0.0 == value(
                sapon.fs.unit.inlet.conc_mol_comp[0, "Ethanol"])

        assert pytest.approx(320.2, abs=1e-1) == \
            value(sapon.fs.unit.outlet.temperature[0])

        assert pytest.approx(101325, abs=1e2) == \
            value(sapon.fs.unit.outlet.pressure[0])

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, sapon):
        assert abs(value(sapon.fs.unit.inlet.flow_vol[0] -
                         sapon.fs.unit.outlet.flow_vol[0])) <= 1e-6

        assert abs(value(
            sapon.fs.unit.outlet.flow_vol[0] *
            sapon.fs.properties.dens_mol*sapon.fs.properties.cp_mol *
            (sapon.fs.unit.inlet.temperature[0] -
             sapon.fs.unit.outlet.temperature[0]) +
            sapon.fs.unit.heat_duty[0])) <= 1e-3

    @pytest.mark.ui
    def test_report(self, sapon):
        sapon.fs.unit.report()
