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
Tests for saponification property package example.
Authors: Andrew Lee
"""
import logging
import pytest
from pyomo.environ import (ConcreteModel,
                           Constraint,
                           Param,
                           value,
                           Var)
from idaes.core import MaterialFlowBasis

from idaes.generic_models.properties.examples.saponification_reactions import (
    SaponificationReactionParameterBlock, ReactionBlock)
from idaes.generic_models.properties.examples.saponification_thermo import (
    SaponificationParameterBlock)

from idaes.core.util.testing import get_default_solver


# -----------------------------------------------------------------------------
# Get default solver for testing
solver = get_default_solver()


class TestParamBlock(object):
    @pytest.fixture(scope="class")
    def model(self):
        model = ConcreteModel()
        model.pparams = SaponificationParameterBlock()
        model.rparams = SaponificationReactionParameterBlock(
                default={"property_package": model.pparams})

        return model

    def test_config(self, model):
        assert len(model.rparams.config) == 2

    def test_build(self, model):
        assert model.rparams.reaction_block_class is ReactionBlock

        assert len(model.rparams.phase_list) == 1
        for i in model.rparams.phase_list:
            assert i == "Liq"

        assert len(model.rparams.component_list) == 5
        for i in model.rparams.component_list:
            assert i in ['H2O',
                         'NaOH',
                         'EthylAcetate',
                         'SodiumAcetate',
                         'Ethanol']

        assert len(model.rparams.rate_reaction_idx) == 1
        for i in model.rparams.rate_reaction_idx:
            assert i == "R1"

        assert len(model.rparams.rate_reaction_stoichiometry) == 5
        for i in model.rparams.rate_reaction_stoichiometry:
            assert i in [("R1", "Liq", "NaOH"),
                         ("R1", "Liq", "EthylAcetate"),
                         ("R1", "Liq", "SodiumAcetate"),
                         ("R1", "Liq", "Ethanol"),
                         ("R1", "Liq", "H2O")]

        assert isinstance(model.rparams.arrhenius, Param)
        assert value(model.rparams.arrhenius) == 3.132e6

        assert isinstance(model.rparams.energy_activation, Param)
        assert value(model.rparams.energy_activation) == 43000

        assert isinstance(model.rparams.dh_rxn, Param)
        assert len(model.rparams.dh_rxn) == 1
        for i in model.rparams.dh_rxn:
            assert value(model.rparams.dh_rxn[i]) == -49000


class TestReactionBlock(object):
    @pytest.fixture(scope="class")
    def model(self):
        model = ConcreteModel()
        model.pparams = SaponificationParameterBlock()
        model.rparams = SaponificationReactionParameterBlock(
                default={"property_package": model.pparams})

        model.props = model.pparams.state_block_class(
                [1],
                default={"parameters": model.pparams})

        model.rxns = model.rparams.reaction_block_class(
                [1],
                default={"parameters": model.rparams,
                         "state_block": model.props})

        return model

    def test_build(self, model):
        assert model.rxns[1].conc_mol_comp_ref is model.props[1].conc_mol_comp
        assert model.rxns[1].temperature_ref is model.props[1].temperature
        assert model.rxns[1].dh_rxn is model.rparams.dh_rxn

    def test_rate_constant(self, model):
        assert isinstance(model.rxns[1].k_rxn, Var)
        assert isinstance(model.rxns[1].arrhenius_eqn, Constraint)

    def test_rxn_rate(self, model):
        assert isinstance(model.rxns[1].reaction_rate, Var)
        assert isinstance(model.rxns[1].rate_expression, Constraint)

    def test_get_reaction_rate_basis(self, model):
        assert model.rxns[1].get_reaction_rate_basis() == \
            MaterialFlowBasis.molar

    def test_model_check(self, model):
        assert model.rxns[1].model_check() is None

    def test_initialize(self, model):
        assert model.rxns.initialize(outlvl=1) is None
