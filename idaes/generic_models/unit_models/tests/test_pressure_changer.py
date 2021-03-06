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
Tests for Pressure Changer unit model.

Author: Andrew Lee, Emmanuel Ogbe
"""
import pytest

from pyomo.environ import (ConcreteModel,
                           Constraint,
                           TerminationCondition,
                           SolverStatus,
                           value,
                           Var)

from idaes.core import (FlowsheetBlock,
                        MaterialBalanceType,
                        EnergyBalanceType,
                        MomentumBalanceType)

from idaes.generic_models.unit_models.pressure_changer import (
    PressureChanger,
    PressureChangerData,
    Turbine,
    Compressor,
    Pump,
    ThermodynamicAssumption,
)

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
from idaes.core.util.exceptions import BalanceTypeNotSupportedError


# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_default_solver()


# -----------------------------------------------------------------------------
def test_ThermodynamicAssumption():
    assert len(ThermodynamicAssumption) == 4


class TestPressureChanger(object):
    def test_config(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties})

        # Check unit config arguments
        assert len(m.fs.unit.config) == 10

        assert m.fs.unit.config.material_balance_type == \
            MaterialBalanceType.useDefault
        assert m.fs.unit.config.energy_balance_type == \
            EnergyBalanceType.useDefault
        assert m.fs.unit.config.momentum_balance_type == \
            MomentumBalanceType.pressureTotal
        assert not m.fs.unit.config.has_phase_equilibrium
        assert m.fs.unit.config.compressor
        assert m.fs.unit.config.thermodynamic_assumption == \
            ThermodynamicAssumption.isothermal
        assert m.fs.unit.config.property_package is m.fs.properties

    def test_dynamic_build(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": True})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties})

        assert hasattr(m.fs.unit, "volume")

    def test_pump(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.pump})

        assert isinstance(m.fs.unit.fluid_work_calculation, Constraint)

    def test_adiabatic(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.adiabatic})

        assert isinstance(m.fs.unit.adiabatic, Constraint)

    def test_isentropic_comp_phase_balances(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "material_balance_type": MaterialBalanceType.componentPhase})

        assert isinstance(m.fs.unit.state_material_balances, Constraint)
        assert len(m.fs.unit.state_material_balances) == 4

    def test_isentropic_comp_total_balances(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "material_balance_type": MaterialBalanceType.componentTotal})

        assert isinstance(m.fs.unit.state_material_balances, Constraint)
        assert len(m.fs.unit.state_material_balances) == 2

    def test_isentropic_total_balances(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        with pytest.raises(BalanceTypeNotSupportedError):
            m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "material_balance_type": MaterialBalanceType.total})

    def test_isentropic_total_element_balances(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        with pytest.raises(BalanceTypeNotSupportedError):
            m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "material_balance_type": MaterialBalanceType.elementTotal})

    def test_isentropic_material_balances_none(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        with pytest.raises(BalanceTypeNotSupportedError):
            m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "material_balance_type": MaterialBalanceType.none})


# -----------------------------------------------------------------------------
class TestBTX_isothermal(object):
    @pytest.fixture(scope="class")
    def btx(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = BTXParameterBlock(default={"valid_phase": 'Liq'})

        m.fs.unit = PressureChanger(default={
            "property_package": m.fs.properties,
            "thermodynamic_assumption": ThermodynamicAssumption.isothermal})

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

        assert hasattr(btx.fs.unit, "work_mechanical")
        assert hasattr(btx.fs.unit, "deltaP")
        assert isinstance(btx.fs.unit.ratioP, Var)
        assert isinstance(btx.fs.unit.ratioP_calculation, Constraint)

        assert number_variables(btx) == 25
        assert number_total_constraints(btx) == 19
        assert number_unused_variables(btx) == 0

    def test_dof(self, btx):
        btx.fs.unit.inlet.flow_mol[0].fix(5)  # mol/s
        btx.fs.unit.inlet.temperature[0].fix(365)  # K
        btx.fs.unit.inlet.pressure[0].fix(101325)  # Pa
        btx.fs.unit.inlet.mole_frac_comp[0, "benzene"].fix(0.5)
        btx.fs.unit.inlet.mole_frac_comp[0, "toluene"].fix(0.5)

        btx.fs.unit.deltaP.fix(50000)

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
        assert (pytest.approx(365, abs=1e-2) ==
                value(btx.fs.unit.outlet.temperature[0]))
        assert (pytest.approx(151325, abs=1e2) ==
                value(btx.fs.unit.outlet.pressure[0]))
        assert (pytest.approx(0, abs=1e-6) ==
                value(btx.fs.unit.work_mechanical[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, btx):
        assert abs(value(btx.fs.unit.inlet.flow_mol[0] -
                         btx.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert abs(btx.fs.unit.outlet.flow_mol[0] *
                   (btx.fs.unit.control_volume.properties_in[0]
                    .enth_mol_phase['Liq'] -
                    btx.fs.unit.control_volume.properties_out[0]
                    .enth_mol_phase['Liq'])) <= 1e-6

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

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "compressor": True})

        return m

    @pytest.fixture(scope="class")
    def iapws_turb(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = iapws95.Iapws95ParameterBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.isentropic,
                "compressor": False})

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

        assert hasattr(iapws.fs.unit, "work_mechanical")
        assert hasattr(iapws.fs.unit, "deltaP")
        assert isinstance(iapws.fs.unit.ratioP, Var)
        assert isinstance(iapws.fs.unit.ratioP_calculation, Constraint)

        assert isinstance(iapws.fs.unit.efficiency_isentropic, Var)
        assert isinstance(iapws.fs.unit.work_isentropic, Var)

        assert hasattr(iapws.fs.unit, "properties_isentropic")
        assert isinstance(iapws.fs.unit.isentropic_pressure, Constraint)
        assert isinstance(iapws.fs.unit.state_material_balances, Constraint)
        assert isinstance(iapws.fs.unit.isentropic, Constraint)
        assert isinstance(iapws.fs.unit.isentropic_energy_balance, Constraint)
        assert isinstance(iapws.fs.unit.actual_work, Constraint)

        assert number_variables(iapws) == 14
        assert number_total_constraints(iapws) == 9
        assert number_unused_variables(iapws) == 0

    def test_dof(self, iapws):
        iapws.fs.unit.inlet.flow_mol[0].fix(100)
        iapws.fs.unit.inlet.enth_mol[0].fix(4000)
        iapws.fs.unit.inlet.pressure[0].fix(101325)

        iapws.fs.unit.deltaP.fix(50000)
        iapws.fs.unit.efficiency_isentropic.fix(0.9)

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
        # Check that outlet and isentropic pressure are equal
        assert pytest.approx(
            value(iapws.fs.unit.properties_isentropic[0].pressure), 1e-6) == \
            value(iapws.fs.unit.outlet.pressure[0])

        # Check that inlet and isentropic entropies are equal
        assert pytest.approx(
            value(iapws.fs.unit.properties_isentropic[0].entr_mol), 1e-6) == \
            value(iapws.fs.unit.control_volume.properties_in[0].entr_mol)

        assert pytest.approx(100, abs=1e-5) == \
            value(iapws.fs.unit.outlet.flow_mol[0])

        assert pytest.approx(4002, abs=1e0) == \
            value(iapws.fs.unit.outlet.enth_mol[0])

        assert pytest.approx(151325, abs=1e2) == \
            value(iapws.fs.unit.outlet.pressure[0])

        assert pytest.approx(101.43796915073504, abs=1e-1) == \
            value(iapws.fs.unit.work_mechanical[0])

        assert pytest.approx(91.29417223566153, abs=1e-1) == \
            value(iapws.fs.unit.work_isentropic[0])

        # For verification, check outlet and isentropic temperatures
        assert pytest.approx(326.170, 1e-5) == \
            value(iapws.fs.unit.control_volume.properties_out[0].temperature)

        assert pytest.approx(326.170, 1e-5) == \
            value(iapws.fs.unit.properties_isentropic[0].temperature)

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, iapws):
        assert abs(value(iapws.fs.unit.inlet.flow_mol[0] -
                         iapws.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert abs(value(
                iapws.fs.unit.outlet.flow_mol[0] *
                (iapws.fs.unit.inlet.enth_mol[0] -
                 iapws.fs.unit.outlet.enth_mol[0]) +
                iapws.fs.unit.work_mechanical[0])) <= 1e-6

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_verify(self, iapws_turb):
        iapws=iapws_turb
        # Verify the turbine results against 3 known test cases

        # Case Data (90% isentropic efficency)
        # Run with Aspen Plus v10 using iapws-95
        cases = {
            "F": (1000,1000,1000), # mol/s
            "Tin": (500, 800, 400), # K
            "Pin": (1000, 10000, 200), # kPa
            "W": (-1224.64, -1911.55, -1010.64), # kW
            "Tout": (463.435, 742.992, 382.442), # K
            "Pout": (700, 7000, 140), # kPa
            "xout": (1.0, 1.0, 0.9886), # vapor fraction
            "Tisen": (460.149, 738.224, 382.442),
        }

        for i in [0,1,2]:
            F = cases["F"][i]
            Tin = cases["Tin"][i]
            Tout = cases["Tout"][i]
            Pin = cases["Pin"][i]*1000
            Pout = cases["Pout"][i]*1000
            hin = iapws95.htpx(T=Tin, P=Pin)
            W = cases["W"][i]*1000
            Tis = cases["Tisen"][i]
            xout = cases["xout"][i]

            iapws.fs.unit.inlet.flow_mol[0].fix(F)
            iapws.fs.unit.inlet.enth_mol[0].fix(hin)
            iapws.fs.unit.inlet.pressure[0].fix(Pin)
            iapws.fs.unit.deltaP.fix(Pout - Pin)
            iapws.fs.unit.efficiency_isentropic.fix(0.9)
            iapws.fs.unit.initialize(optarg={'tol': 1e-6})
            results = solver.solve(iapws)
            # Check for optimal solution
            assert results.solver.termination_condition == \
                TerminationCondition.optimal
            assert results.solver.status == SolverStatus.ok

            Tout = pytest.approx(cases["Tout"][i], rel=1e-2)
            Pout = pytest.approx(cases["Pout"][i]*1000, rel=1e-2)
            Pout = pytest.approx(cases["Pout"][i]*1000, rel=1e-2)
            W = pytest.approx(cases["W"][i]*1000, rel=1e-2)
            xout = pytest.approx(xout, rel=1e-2)
            prop_out = iapws.fs.unit.control_volume.properties_out[0]
            prop_in = iapws.fs.unit.control_volume.properties_in[0]
            prop_is = iapws.fs.unit.properties_isentropic[0]

            assert value(prop_in.temperature) == pytest.approx(Tin, rel=1e-3)
            assert value(prop_is.temperature) == pytest.approx(Tis, rel=1e-3)
            assert value(iapws.fs.unit.control_volume.work[0]) == W
            assert value(prop_out.pressure) == Pout
            assert value(prop_out.temperature) == Tout
            assert value(prop_out.vapor_frac) == xout


    @pytest.mark.ui
    def test_report(self, iapws):
        iapws.fs.unit.report()


# -----------------------------------------------------------------------------
class TestSaponification(object):
    @pytest.fixture(scope="class")
    def sapon(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = SaponificationParameterBlock()

        m.fs.unit = PressureChanger(default={
                "property_package": m.fs.properties,
                "thermodynamic_assumption": ThermodynamicAssumption.pump,
                "compressor": False})

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

        assert hasattr(sapon.fs.unit, "work_mechanical")
        assert hasattr(sapon.fs.unit, "deltaP")
        assert isinstance(sapon.fs.unit.ratioP, Var)
        assert isinstance(sapon.fs.unit.ratioP_calculation, Constraint)

        assert isinstance(sapon.fs.unit.efficiency_pump, Var)
        assert isinstance(sapon.fs.unit.work_fluid, Var)
        assert isinstance(sapon.fs.unit.fluid_work_calculation, Constraint)
        assert isinstance(sapon.fs.unit.actual_work, Constraint)

        assert number_variables(sapon) == 21
        assert number_total_constraints(sapon) == 11
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

        sapon.fs.unit.deltaP.fix(-20000)
        sapon.fs.unit.efficiency_pump.fix(0.9)

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

        assert pytest.approx(55388.0, abs=1e-2) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "H2O"])
        assert pytest.approx(100.0, abs=1e-2) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "NaOH"])
        assert pytest.approx(100.0, abs=1e-2) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "EthylAcetate"])
        assert pytest.approx(0.0, abs=1e-2) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "SodiumAcetate"])
        assert pytest.approx(0.0, abs=1e-2) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "Ethanol"])

        assert pytest.approx(320.0, abs=1e-1) == \
            value(sapon.fs.unit.outlet.temperature[0])

        assert pytest.approx(81325, abs=1e2) == \
            value(sapon.fs.unit.outlet.pressure[0])

        assert pytest.approx(-18.0, abs=1e-2) == \
            value(sapon.fs.unit.work_mechanical[0])
        assert pytest.approx(-20.0, abs=1e-2) == \
            value(sapon.fs.unit.work_fluid[0])

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, sapon):
        assert abs(value(
                sapon.fs.unit.outlet.flow_vol[0] *
                sapon.fs.properties.dens_mol*sapon.fs.properties.cp_mol *
                (sapon.fs.unit.inlet.temperature[0] -
                 sapon.fs.unit.outlet.temperature[0]) +
                sapon.fs.unit.work_mechanical[0])) <= 1e-4

    @pytest.mark.ui
    def test_report(self, sapon):
        sapon.fs.unit.report()

class TestTurbine(object):
    def test_config(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = Turbine(default={
                "property_package": m.fs.properties})

        assert isinstance(m.fs.unit, PressureChangerData)
        # Check unit config arguments
        assert len(m.fs.unit.config) == 10

        assert m.fs.unit.config.material_balance_type == \
            MaterialBalanceType.useDefault
        assert m.fs.unit.config.energy_balance_type == \
            EnergyBalanceType.useDefault
        assert m.fs.unit.config.momentum_balance_type == \
            MomentumBalanceType.pressureTotal
        assert not m.fs.unit.config.has_phase_equilibrium
        assert not m.fs.unit.config.compressor
        assert m.fs.unit.config.thermodynamic_assumption == \
            ThermodynamicAssumption.isentropic
        assert m.fs.unit.config.property_package is m.fs.properties

class TestCompressor(object):
    def test_config(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = Compressor(default={
                "property_package": m.fs.properties})

        assert isinstance(m.fs.unit, PressureChangerData)
        # Check unit config arguments
        assert len(m.fs.unit.config) == 10

        assert m.fs.unit.config.material_balance_type == \
            MaterialBalanceType.useDefault
        assert m.fs.unit.config.energy_balance_type == \
            EnergyBalanceType.useDefault
        assert m.fs.unit.config.momentum_balance_type == \
            MomentumBalanceType.pressureTotal
        assert not m.fs.unit.config.has_phase_equilibrium
        assert m.fs.unit.config.compressor
        assert m.fs.unit.config.thermodynamic_assumption == \
            ThermodynamicAssumption.isentropic
        assert m.fs.unit.config.property_package is m.fs.properties

class TestPump(object):
    def test_config(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = PhysicalParameterTestBlock()

        m.fs.unit = Pump(default={
                "property_package": m.fs.properties})

        assert isinstance(m.fs.unit, PressureChangerData)
        # Check unit config arguments
        assert len(m.fs.unit.config) == 10

        assert m.fs.unit.config.material_balance_type == \
            MaterialBalanceType.useDefault
        assert m.fs.unit.config.energy_balance_type == \
            EnergyBalanceType.useDefault
        assert m.fs.unit.config.momentum_balance_type == \
            MomentumBalanceType.pressureTotal
        assert not m.fs.unit.config.has_phase_equilibrium
        assert m.fs.unit.config.compressor
        assert m.fs.unit.config.thermodynamic_assumption == \
            ThermodynamicAssumption.pump
        assert m.fs.unit.config.property_package is m.fs.properties
