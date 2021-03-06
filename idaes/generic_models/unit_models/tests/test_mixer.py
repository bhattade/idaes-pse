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
                           Constraint,
                           Param,
                           Set,
                           Var,
                           TerminationCondition,
                           SolverStatus,
                           value)
from pyomo.network import Port
from pyomo.common.config import ConfigBlock

from idaes.core import (FlowsheetBlock,
                        StateBlock,
                        declare_process_block_class)
from idaes.generic_models.properties.activity_coeff_models.BTX_activity_coeff_VLE \
    import BTXParameterBlock
from idaes.generic_models.properties import iapws95
from idaes.generic_models.properties.examples.saponification_thermo import \
    SaponificationParameterBlock

from idaes.generic_models.unit_models.mixer import (Mixer,
                                     MixerData,
                                     MixingType,
                                     MaterialBalanceType,
                                     MomentumMixingType)
from idaes.core.util.exceptions import (BurntToast,
                                        ConfigurationError,
                                        PropertyNotSupportedError)
from idaes.core.util.model_statistics import (degrees_of_freedom,
                                              number_variables,
                                              number_total_constraints,
                                              fixed_variables_set,
                                              activated_constraints_set,
                                              number_unused_variables)
from idaes.core.util.testing import (get_default_solver,
                                     PhysicalParameterTestBlock,
                                     TestStateBlock)


# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_default_solver()


# -----------------------------------------------------------------------------
# Unit Tests for Mixer
class TestMixer(object):
    @declare_process_block_class("MixerFrame")
    class MixerFrameData(MixerData):
        def build(self):
            super(MixerData, self).build()

    @pytest.fixture(scope="function")
    def mixer_frame(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()

        m.fs.mix = MixerFrame(default={"property_package": m.fs.pp})

        return m

    def test_mixer_config(self, mixer_frame):
        assert len(mixer_frame.fs.mix.config) == 12
        assert mixer_frame.fs.mix.config.dynamic is False
        assert mixer_frame.fs.mix.config.has_holdup is False
        assert mixer_frame.fs.mix.config.property_package == mixer_frame.fs.pp
        assert isinstance(mixer_frame.fs.mix.config.property_package_args,
                          ConfigBlock)
        assert len(mixer_frame.fs.mix.config.property_package_args) == 0
        assert mixer_frame.fs.mix.config.inlet_list is None
        assert mixer_frame.fs.mix.config.num_inlets is None
        assert mixer_frame.fs.mix.config.has_phase_equilibrium is False
        assert mixer_frame.fs.mix.config.energy_mixing_type == \
            MixingType.extensive
        assert mixer_frame.fs.mix.config.momentum_mixing_type == \
            MomentumMixingType.minimize
        assert mixer_frame.fs.mix.config.mixed_state_block is None
        assert mixer_frame.fs.mix.config.construct_ports is True
        assert mixer_frame.fs.mix.config.material_balance_type == \
            MaterialBalanceType.useDefault

    def test_inherited_methods(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        assert hasattr(mixer_frame.fs.mix.config.property_package,
                       "phase_list")

    def test_create_inlet_list_default(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()

        for i in inlet_list:
            assert i in ["inlet_1", "inlet_2"]

    def test_create_inlet_list_inlet_list(self, mixer_frame):
        mixer_frame.fs.mix.config.inlet_list = ["foo", "bar"]

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()

        for i in inlet_list:
            assert i in ["foo", "bar"]

    def test_create_inlet_list_num_inlets(self, mixer_frame):
        mixer_frame.fs.mix.config.num_inlets = 3

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()

        for i in inlet_list:
            assert i in ["inlet_1", "inlet_2", "inlet_3"]

    def test_create_inlet_list_both_args_consistent(self, mixer_frame):
        mixer_frame.fs.mix.config.inlet_list = ["foo", "bar"]
        mixer_frame.fs.mix.config.num_inlets = 2

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()

        for i in inlet_list:
            assert i in ["foo", "bar"]

    def test_create_inlet_list_both_args_inconsistent(self, mixer_frame):
        mixer_frame.fs.mix.config.inlet_list = ["foo", "bar"]
        mixer_frame.fs.mix.config.num_inlets = 3

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        with pytest.raises(ConfigurationError):
            mixer_frame.fs.mix.create_inlet_list()

    def test_add_inlet_state_blocks(self, mixer_frame):
        mixer_frame.fs.mix.config.inlet_list = ["foo", "bar"]

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)

        assert isinstance(mixer_frame.fs.mix.foo_state, StateBlock)
        assert isinstance(mixer_frame.fs.mix.bar_state, StateBlock)

        assert len(inlet_blocks) == 2
        for i in inlet_blocks:
            assert isinstance(i, StateBlock)
            assert i.local_name in ["foo_state", "bar_state"]
            assert i[0].config.has_phase_equilibrium is False
            assert i[0].config.defined_state is True
            assert len(i[0].config) == 3

    def test_add_inlet_state_blocks_prop_pack_args(self, mixer_frame):
        mixer_frame.fs.mix.config.property_package_args = {"test": 1}
        mixer_frame.fs.mix.config.inlet_list = ["foo", "bar"]

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)

        assert isinstance(mixer_frame.fs.mix.foo_state, StateBlock)
        assert isinstance(mixer_frame.fs.mix.bar_state, StateBlock)

        assert len(inlet_blocks) == 2
        for i in inlet_blocks:
            assert isinstance(i, StateBlock)
            assert i.local_name in ["foo_state", "bar_state"]
            assert i[0].config.has_phase_equilibrium is False
            assert i[0].config.defined_state is True
            assert len(i[0].config) == 4
            assert i[0].config.test == 1

    def test_add_mixed_state_block(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        assert isinstance(mixed_block, StateBlock)
        assert hasattr(mixer_frame.fs.mix, "mixed_state")
        assert not mixer_frame.fs.mix.mixed_state[0].config.has_phase_equilibrium
        assert mixer_frame.fs.mix.mixed_state[0].config.defined_state is False
        assert len(mixer_frame.fs.mix.mixed_state[0].config) == 3

    def test_add_mixed_state_block_prop_pack_args(self, mixer_frame):
        mixer_frame.fs.mix.config.property_package_args = {"test": 1}

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        assert isinstance(mixed_block, StateBlock)
        assert hasattr(mixer_frame.fs.mix, "mixed_state")
        assert not mixer_frame.fs.mix.mixed_state[0].config.has_phase_equilibrium
        assert mixer_frame.fs.mix.mixed_state[0].config.defined_state is False
        assert len(mixer_frame.fs.mix.mixed_state[0].config) == 4
        assert mixer_frame.fs.mix.mixed_state[0].config.test == 1

    def test_get_mixed_state_block(self, mixer_frame):
        mixer_frame.fs.sb = TestStateBlock(
                mixer_frame.fs.time,
                default={"parameters": mixer_frame.fs.pp})

        mixer_frame.fs.mix.config.mixed_state_block = mixer_frame.fs.sb

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        mixed_block = mixer_frame.fs.mix.get_mixed_state_block()

        assert mixed_block == mixer_frame.fs.sb

    def test_get_mixed_state_block_none(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        with pytest.raises(BurntToast):
            mixer_frame.fs.mix.get_mixed_state_block()

    def test_get_mixed_state_block_mismatch(self, mixer_frame):
        mixer_frame.fs.sb = TestStateBlock(
                mixer_frame.fs.time,
                default={"parameters": mixer_frame.fs.pp})

        # Change parameters arg to create mismatch
        mixer_frame.fs.sb[0].config.parameters = None

        mixer_frame.fs.mix.config.mixed_state_block = mixer_frame.fs.sb

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        with pytest.raises(ConfigurationError):
            mixer_frame.fs.mix.get_mixed_state_block()

    # Test mixing equation methods
    def test_add_material_mixing_equations_pc(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.componentPhase)

        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 4

    def test_add_material_mixing_equations_pc_equilibrium(self, mixer_frame):
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.componentPhase)

        assert isinstance(mixer_frame.fs.mix.phase_equilibrium_generation,
                          Var)
        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 4

    def test_add_material_mixing_equations_pc_equilibrium_not_supported(
            self, mixer_frame):
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        # Remove phase equilibrium list to trigger error
        mixer_frame.fs.pp.del_component(
                mixer_frame.fs.pp.phase_equilibrium_idx)

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        with pytest.raises(PropertyNotSupportedError):
            mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.componentPhase)

    def test_add_material_mixing_equations_tc(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.componentTotal

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.componentTotal)

        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 2

    def test_add_material_mixing_equations_tc_equilibrium(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.componentTotal
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.componentTotal)

        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 2

    def test_add_material_mixing_equations_t(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.total

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.total)

        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 1

    def test_add_material_mixing_equations_t_equilibrium(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.total
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.total)

        assert isinstance(mixer_frame.fs.mix.material_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.material_mixing_equations) == 1

    def test_add_material_mixing_equations_e(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.elementTotal
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        with pytest.raises(ConfigurationError):
            mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.elementTotal)

    def test_add_material_mixing_equations_none(self, mixer_frame):
        mixer_frame.fs.mix.config.material_balance_type = \
            MaterialBalanceType.none
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_material_mixing_equations(
                inlet_blocks, mixed_block, MaterialBalanceType.none)

        assert not hasattr(mixer_frame.fs.mix, "material_mixing_equations")

    def test_add_energy_mixing_equations(self, mixer_frame):
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_energy_mixing_equations(inlet_blocks,
                                                       mixed_block)

        assert isinstance(mixer_frame.fs.mix.enthalpy_mixing_equations,
                          Constraint)
        assert len(mixer_frame.fs.mix.enthalpy_mixing_equations) == 1

    def test_add_pressure_minimization_equations(self, mixer_frame):
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_pressure_minimization_equations(inlet_blocks,
                                                               mixed_block)

        assert isinstance(mixer_frame.fs.mix.inlet_idx, Set)
        assert isinstance(mixer_frame.fs.mix.minimum_pressure, Var)
        assert len(mixer_frame.fs.mix.minimum_pressure) == 2
        assert isinstance(mixer_frame.fs.mix.eps_pressure, Param)
        assert isinstance(mixer_frame.fs.mix.minimum_pressure_constraint,
                          Constraint)
        assert len(mixer_frame.fs.mix.minimum_pressure) == 2
        assert isinstance(mixer_frame.fs.mix.mixture_pressure, Constraint)

    def test_add_pressure_equality_equations(self, mixer_frame):
        mixer_frame.fs.mix.config.has_phase_equilibrium = True

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_pressure_equality_equations(inlet_blocks,
                                                           mixed_block)

        assert isinstance(mixer_frame.fs.mix.pressure_equality_constraints,
                          Constraint)
        assert len(mixer_frame.fs.mix.pressure_equality_constraints) == 2

    def test_add_port_objects(self, mixer_frame):
        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_port_objects(inlet_list,
                                            inlet_blocks,
                                            mixed_block)

        assert isinstance(mixer_frame.fs.mix.inlet_1, Port)
        assert isinstance(mixer_frame.fs.mix.inlet_2, Port)
        assert isinstance(mixer_frame.fs.mix.outlet, Port)

    def test_add_port_objects_construct_ports_False(self, mixer_frame):
        mixer_frame.fs.mix.config.construct_ports = False

        mixer_frame.fs.mix._get_property_package()
        mixer_frame.fs.mix._get_indexing_sets()

        inlet_list = mixer_frame.fs.mix.create_inlet_list()
        inlet_blocks = mixer_frame.fs.mix.add_inlet_state_blocks(inlet_list)
        mixed_block = mixer_frame.fs.mix.add_mixed_state_block()

        mixer_frame.fs.mix.add_port_objects(inlet_list,
                                            inlet_blocks,
                                            mixed_block)

        assert hasattr(mixer_frame.fs.mix, "inlet_1") is False
        assert hasattr(mixer_frame.fs.mix, "inlet_2") is False
        assert hasattr(mixer_frame.fs.mix, "outlet") is False

    # -------------------------------------------------------------------------
    # Test build method
    @pytest.mark.build
    def test_build_default(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()

        m.fs.mix = Mixer(default={"property_package": m.fs.pp})

        assert isinstance(m.fs.mix.material_mixing_equations, Constraint)
        assert len(m.fs.mix.material_mixing_equations) == 4
        assert hasattr(m.fs.mix, "phase_equilibrium_idx_ref") is False

        assert isinstance(m.fs.mix.enthalpy_mixing_equations, Constraint)
        assert len(m.fs.mix.enthalpy_mixing_equations) == 1

        assert isinstance(m.fs.mix.inlet_idx, Set)
        assert isinstance(m.fs.mix.minimum_pressure, Var)
        assert len(m.fs.mix.minimum_pressure) == 2
        assert isinstance(m.fs.mix.eps_pressure, Param)
        assert isinstance(m.fs.mix.minimum_pressure_constraint, Constraint)
        assert len(m.fs.mix.minimum_pressure) == 2
        assert isinstance(m.fs.mix.mixture_pressure, Constraint)

        assert isinstance(m.fs.mix.inlet_1, Port)
        assert isinstance(m.fs.mix.inlet_2, Port)
        assert isinstance(m.fs.mix.outlet, Port)

    @pytest.mark.build
    def test_build_phase_equilibrium(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()

        m.fs.mix = Mixer(default={"property_package": m.fs.pp,
                                  "has_phase_equilibrium": True})

        assert isinstance(m.fs.mix.material_mixing_equations, Constraint)
        assert len(m.fs.mix.material_mixing_equations) == 4
        assert isinstance(m.fs.mix.phase_equilibrium_generation, Var)

        assert isinstance(m.fs.mix.enthalpy_mixing_equations, Constraint)
        assert len(m.fs.mix.enthalpy_mixing_equations) == 1

        assert isinstance(m.fs.mix.inlet_idx, Set)
        assert isinstance(m.fs.mix.minimum_pressure, Var)
        assert len(m.fs.mix.minimum_pressure) == 2
        assert isinstance(m.fs.mix.eps_pressure, Param)
        assert isinstance(m.fs.mix.minimum_pressure_constraint, Constraint)
        assert len(m.fs.mix.minimum_pressure) == 2
        assert isinstance(m.fs.mix.mixture_pressure, Constraint)

        assert isinstance(m.fs.mix.inlet_1, Port)
        assert isinstance(m.fs.mix.inlet_2, Port)
        assert isinstance(m.fs.mix.outlet, Port)

    @pytest.mark.build
    def test_build_phase_pressure_equality(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()

        m.fs.mix = Mixer(default={
                "property_package": m.fs.pp,
                "momentum_mixing_type": MomentumMixingType.equality})

        assert isinstance(m.fs.mix.material_mixing_equations, Constraint)
        assert len(m.fs.mix.material_mixing_equations) == 4

        assert isinstance(m.fs.mix.enthalpy_mixing_equations, Constraint)
        assert len(m.fs.mix.enthalpy_mixing_equations) == 1

        assert isinstance(m.fs.mix.pressure_equality_constraints, Constraint)
        assert len(m.fs.mix.pressure_equality_constraints) == 2

        assert isinstance(m.fs.mix.inlet_1, Port)
        assert isinstance(m.fs.mix.inlet_2, Port)
        assert isinstance(m.fs.mix.outlet, Port)

    # -------------------------------------------------------------------------
    # Test models checks, initialize and release state methods
    def test_model_checks(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()

        m.fs.mix = Mixer(default={
                "property_package": m.fs.pp,
                "momentum_mixing_type": MomentumMixingType.equality})

        m.fs.mix.model_check()

        assert m.fs.mix.inlet_1_state[0].check is True
        assert m.fs.mix.inlet_2_state[0].check is True
        assert m.fs.mix.mixed_state[0].check is True

    @pytest.mark.initialization
    def test_initialize(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()
        m.fs.sb = TestStateBlock(m.fs.time, default={"parameters": m.fs.pp})

        m.fs.mix = Mixer(default={
                "property_package": m.fs.pp,
                "mixed_state_block": m.fs.sb})

        # Change one inlet pressure to check initialization calculations
        m.fs.mix.inlet_1_state[0].pressure = 8e4

        f = m.fs.mix.initialize(hold_state=True)

        assert m.fs.mix.inlet_1_state[0].init_test is True
        assert m.fs.mix.inlet_2_state[0].init_test is True
        assert m.fs.sb[0].init_test is True
        assert m.fs.mix.inlet_1_state[0].hold_state is True
        assert m.fs.mix.inlet_2_state[0].hold_state is True
        assert m.fs.sb[0].hold_state is False

        assert m.fs.sb[0].flow_mol_phase_comp["p1", "c1"].value == 4
        assert m.fs.sb[0].flow_mol_phase_comp["p1", "c2"].value == 4
        assert m.fs.sb[0].flow_mol_phase_comp["p2", "c1"].value == 4
        assert m.fs.sb[0].flow_mol_phase_comp["p2", "c2"].value == 4

        assert m.fs.sb[0].temperature.value == 300

        assert m.fs.sb[0].pressure.value == 8e4

        m.fs.mix.release_state(flags=f)

        assert m.fs.mix.inlet_1_state[0].hold_state is False
        assert m.fs.mix.inlet_2_state[0].hold_state is False
        assert m.fs.sb[0].hold_state is False

    @pytest.mark.ui
    def test_report(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})
        m.fs.pp = PhysicalParameterTestBlock()
        m.fs.sb = TestStateBlock(m.fs.time, default={"parameters": m.fs.pp})

        m.fs.mix = Mixer(default={
                "property_package": m.fs.pp})

        m.fs.mix.report()


# -----------------------------------------------------------------------------
class TestBTX(object):
    @pytest.fixture(scope="class")
    def btx(self):
        m = ConcreteModel()
        m.fs = FlowsheetBlock(default={"dynamic": False})

        m.fs.properties = BTXParameterBlock(default={"valid_phase": 'Liq'})

        m.fs.unit = Mixer(default={"property_package": m.fs.properties})

        return m

    @pytest.mark.build
    def test_build(self, btx):
        assert hasattr(btx.fs.unit, "inlet_1")
        assert len(btx.fs.unit.inlet_1.vars) == 4
        assert hasattr(btx.fs.unit.inlet_1, "flow_mol")
        assert hasattr(btx.fs.unit.inlet_1, "mole_frac_comp")
        assert hasattr(btx.fs.unit.inlet_1, "temperature")
        assert hasattr(btx.fs.unit.inlet_1, "pressure")

        assert hasattr(btx.fs.unit, "inlet_2")
        assert len(btx.fs.unit.inlet_2.vars) == 4
        assert hasattr(btx.fs.unit.inlet_2, "flow_mol")
        assert hasattr(btx.fs.unit.inlet_2, "mole_frac_comp")
        assert hasattr(btx.fs.unit.inlet_2, "temperature")
        assert hasattr(btx.fs.unit.inlet_2, "pressure")

        assert hasattr(btx.fs.unit, "outlet")
        assert len(btx.fs.unit.outlet.vars) == 4
        assert hasattr(btx.fs.unit.outlet, "flow_mol")
        assert hasattr(btx.fs.unit.outlet, "mole_frac_comp")
        assert hasattr(btx.fs.unit.outlet, "temperature")
        assert hasattr(btx.fs.unit.outlet, "pressure")

        assert number_variables(btx) == 35
        assert number_total_constraints(btx) == 25
        assert number_unused_variables(btx) == 0

    def test_dof(self, btx):
        btx.fs.unit.inlet_1.flow_mol[0].fix(5)  # mol/s
        btx.fs.unit.inlet_1.temperature[0].fix(365)  # K
        btx.fs.unit.inlet_1.pressure[0].fix(2e5)  # Pa
        btx.fs.unit.inlet_1.mole_frac_comp[0, "benzene"].fix(0.5)
        btx.fs.unit.inlet_1.mole_frac_comp[0, "toluene"].fix(0.5)

        btx.fs.unit.inlet_2.flow_mol[0].fix(1)  # mol/s
        btx.fs.unit.inlet_2.temperature[0].fix(300)  # K
        btx.fs.unit.inlet_2.pressure[0].fix(101325)  # Pa
        btx.fs.unit.inlet_2.mole_frac_comp[0, "benzene"].fix(0.5)
        btx.fs.unit.inlet_2.mole_frac_comp[0, "toluene"].fix(0.5)

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
        assert (pytest.approx(6, abs=1e-3) ==
                value(btx.fs.unit.outlet.flow_mol[0]))
        assert (pytest.approx(354.7, abs=1e-1) ==
                value(btx.fs.unit.outlet.temperature[0]))
        assert (pytest.approx(101325, abs=1e3) ==
                value(btx.fs.unit.outlet.pressure[0]))

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, btx):
        assert abs(value(btx.fs.unit.inlet_1.flow_mol[0] +
                         btx.fs.unit.inlet_2.flow_mol[0] -
                         btx.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert 1e-6 >= abs(value(
                btx.fs.unit.inlet_1.flow_mol[0] *
                btx.fs.unit.inlet_1_state[0].enth_mol_phase['Liq'] +
                btx.fs.unit.inlet_2.flow_mol[0] *
                btx.fs.unit.inlet_2_state[0].enth_mol_phase['Liq'] -
                btx.fs.unit.outlet.flow_mol[0] *
                btx.fs.unit.mixed_state[0].enth_mol_phase['Liq']))

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

        m.fs.unit = Mixer(default={
                "property_package": m.fs.properties,
                "material_balance_type": MaterialBalanceType.componentTotal,
                "momentum_mixing_type": MomentumMixingType.equality})

        return m

    @pytest.mark.build
    def test_build(self, iapws):
        assert len(iapws.fs.unit.inlet_1.vars) == 3
        assert hasattr(iapws.fs.unit.inlet_1, "flow_mol")
        assert hasattr(iapws.fs.unit.inlet_1, "enth_mol")
        assert hasattr(iapws.fs.unit.inlet_1, "pressure")

        assert len(iapws.fs.unit.inlet_2.vars) == 3
        assert hasattr(iapws.fs.unit.inlet_2, "flow_mol")
        assert hasattr(iapws.fs.unit.inlet_2, "enth_mol")
        assert hasattr(iapws.fs.unit.inlet_2, "pressure")

        assert hasattr(iapws.fs.unit, "outlet")
        assert len(iapws.fs.unit.outlet.vars) == 3
        assert hasattr(iapws.fs.unit.outlet, "flow_mol")
        assert hasattr(iapws.fs.unit.outlet, "enth_mol")
        assert hasattr(iapws.fs.unit.outlet, "pressure")

    def test_dof(self, iapws):
        iapws.fs.unit.inlet_1.flow_mol[0].fix(100)
        iapws.fs.unit.inlet_1.enth_mol[0].fix(4000)
        iapws.fs.unit.inlet_1.pressure[0].fix(101325)

        iapws.fs.unit.inlet_2.flow_mol[0].fix(100)
        iapws.fs.unit.inlet_2.enth_mol[0].fix(3500)

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
        assert pytest.approx(200, abs=1e-5) == \
            value(iapws.fs.unit.outlet.flow_mol[0])

        assert pytest.approx(3750, abs=1e0) == \
            value(iapws.fs.unit.outlet.enth_mol[0])

        assert pytest.approx(101325, abs=1e2) == \
            value(iapws.fs.unit.outlet.pressure[0])

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, iapws):
        assert abs(value(iapws.fs.unit.inlet_1.flow_mol[0] +
                         iapws.fs.unit.inlet_2.flow_mol[0] -
                         iapws.fs.unit.outlet.flow_mol[0])) <= 1e-6

        assert abs(value(iapws.fs.unit.inlet_1.flow_mol[0] *
                         iapws.fs.unit.inlet_1.enth_mol[0] +
                         iapws.fs.unit.inlet_2.flow_mol[0] *
                         iapws.fs.unit.inlet_2.enth_mol[0] -
                         iapws.fs.unit.outlet.flow_mol[0] *
                         iapws.fs.unit.outlet.enth_mol[0])) <= 1e-6

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

        m.fs.unit = Mixer(default={"property_package": m.fs.properties})

        return m

    @pytest.mark.build
    def test_build(self, sapon):
        assert len(sapon.fs.unit.inlet_1.vars) == 4
        assert hasattr(sapon.fs.unit.inlet_1, "flow_vol")
        assert hasattr(sapon.fs.unit.inlet_1, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.inlet_1, "temperature")
        assert hasattr(sapon.fs.unit.inlet_1, "pressure")

        assert len(sapon.fs.unit.inlet_2.vars) == 4
        assert hasattr(sapon.fs.unit.inlet_2, "flow_vol")
        assert hasattr(sapon.fs.unit.inlet_2, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.inlet_2, "temperature")
        assert hasattr(sapon.fs.unit.inlet_2, "pressure")

        assert len(sapon.fs.unit.outlet.vars) == 4
        assert hasattr(sapon.fs.unit.outlet, "flow_vol")
        assert hasattr(sapon.fs.unit.outlet, "conc_mol_comp")
        assert hasattr(sapon.fs.unit.outlet, "temperature")
        assert hasattr(sapon.fs.unit.outlet, "pressure")

        assert number_variables(sapon) == 26
        assert number_total_constraints(sapon) == 10
        assert number_unused_variables(sapon) == 0

    def test_dof(self, sapon):
        sapon.fs.unit.inlet_1.flow_vol[0].fix(1e-3)
        sapon.fs.unit.inlet_1.temperature[0].fix(320)
        sapon.fs.unit.inlet_1.pressure[0].fix(101325)
        sapon.fs.unit.inlet_1.conc_mol_comp[0, "H2O"].fix(55388.0)
        sapon.fs.unit.inlet_1.conc_mol_comp[0, "NaOH"].fix(100.0)
        sapon.fs.unit.inlet_1.conc_mol_comp[0, "EthylAcetate"].fix(100.0)
        sapon.fs.unit.inlet_1.conc_mol_comp[0, "SodiumAcetate"].fix(0.0)
        sapon.fs.unit.inlet_1.conc_mol_comp[0, "Ethanol"].fix(0.0)

        sapon.fs.unit.inlet_2.flow_vol[0].fix(1e-3)
        sapon.fs.unit.inlet_2.temperature[0].fix(300)
        sapon.fs.unit.inlet_2.pressure[0].fix(101325)
        sapon.fs.unit.inlet_2.conc_mol_comp[0, "H2O"].fix(55388.0)
        sapon.fs.unit.inlet_2.conc_mol_comp[0, "NaOH"].fix(100.0)
        sapon.fs.unit.inlet_2.conc_mol_comp[0, "EthylAcetate"].fix(100.0)
        sapon.fs.unit.inlet_2.conc_mol_comp[0, "SodiumAcetate"].fix(0.0)
        sapon.fs.unit.inlet_2.conc_mol_comp[0, "Ethanol"].fix(0.0)

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
        assert pytest.approx(2e-3, abs=1e-6) == \
            value(sapon.fs.unit.outlet.flow_vol[0])

        assert pytest.approx(55388.0, abs=1e0) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "H2O"])
        assert pytest.approx(100.0, abs=1e-3) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "NaOH"])
        assert pytest.approx(100.0, abs=1e-3) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "EthylAcetate"])
        assert pytest.approx(0.0, abs=1e-3) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "SodiumAcetate"])
        assert pytest.approx(0.0, abs=1e-3) == value(
                sapon.fs.unit.outlet.conc_mol_comp[0, "Ethanol"])

        assert pytest.approx(310.0, abs=1e-1) == \
            value(sapon.fs.unit.outlet.temperature[0])

        assert pytest.approx(101325, abs=1e2) == \
            value(sapon.fs.unit.outlet.pressure[0])

    @pytest.mark.initialize
    @pytest.mark.solver
    @pytest.mark.skipif(solver is None, reason="Solver not available")
    def test_conservation(self, sapon):
        assert abs(value(sapon.fs.unit.inlet_1.flow_vol[0] +
                         sapon.fs.unit.inlet_2.flow_vol[0] -
                         sapon.fs.unit.outlet.flow_vol[0])) <= 1e-6

        assert abs(value(
                sapon.fs.unit.inlet_1.flow_vol[0] *
                sapon.fs.properties.dens_mol*sapon.fs.properties.cp_mol *
                (sapon.fs.unit.inlet_1.temperature[0] -
                 sapon.fs.properties.temperature_ref) +
                sapon.fs.unit.inlet_2.flow_vol[0] *
                sapon.fs.properties.dens_mol*sapon.fs.properties.cp_mol *
                (sapon.fs.unit.inlet_2.temperature[0] -
                 sapon.fs.properties.temperature_ref) -
                sapon.fs.unit.outlet.flow_vol[0] *
                sapon.fs.properties.dens_mol*sapon.fs.properties.cp_mol *
                (sapon.fs.unit.outlet.temperature[0] -
                 sapon.fs.properties.temperature_ref))) <= 1e-3

    @pytest.mark.ui
    def test_report(self, sapon):
        sapon.fs.unit.report()
