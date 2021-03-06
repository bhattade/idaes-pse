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
Base class for control volumes
"""

# Import Pyomo libraries
from pyomo.environ import Constraint, Param, Reals, Var
from pyomo.dae import DerivativeVar

# Import IDAES cores
from idaes.core import (declare_process_block_class,
                        ControlVolumeBlockData,
                        FlowDirection,
                        MaterialFlowBasis,
                        MaterialBalanceType)
from idaes.core.util.exceptions import (BalanceTypeNotSupportedError,
                                        BurntToast,
                                        ConfigurationError,
                                        PropertyNotSupportedError,
                                        PropertyPackageError)
from idaes.core.util.tables import create_stream_table_dataframe

import idaes.logger as idaeslog

__author__ = "Andrew Lee"


_log = idaeslog.getLogger(__name__)

# TODO : Custom terms in material balances, other types of material balances
# TODO : Improve flexibility for get_material_flow_terms and associated


@declare_process_block_class("ControlVolume0DBlock", doc="""
    ControlVolume0DBlock is a specialized Pyomo block for IDAES non-discretized
    control volume blocks, and contains instances of ControlVolume0DBlockData.

    ControlVolume0DBlock should be used for any control volume with a defined
    volume and distinct inlets and outlets which does not require spatial
    discretization. This encompases most basic unit models used in process
    modeling.""")
class ControlVolume0DBlockData(ControlVolumeBlockData):
    """
    0-Dimensional (Non-Discretised) ControlVolume Class

    This class forms the core of all non-discretized IDAES models. It provides
    methods to build property and reaction blocks, and add mass, energy and
    momentum balances. The form of the terms used in these constraints is
    specified in the chosen property package.
    """
    def build(self):
        """
        Build method for ControlVolume0DBlock blocks.

        Returns:
            None
        """
        # Call build method from base class
        super(ControlVolume0DBlockData, self).build()

    def add_geometry(self):
        """
        Method to create volume Var in ControlVolume.

        Args:
            None

        Returns:
            None
        """
        l_units = self.config.property_package.get_metadata().default_units[
                                                                      "length"]
        self.volume = Var(self.flowsheet().config.time, initialize=1.0,
                          doc='Holdup Volume [{}^3]'.format(l_units))

    def add_state_blocks(self,
                         information_flow=FlowDirection.forward,
                         has_phase_equilibrium=None):
        """
        This method constructs the inlet and outlet state blocks for the
        control volume.

        Args:
            information_flow: a FlowDirection Enum indicating whether
                               information flows from inlet-to-outlet or
                               outlet-to-inlet
            has_phase_equilibrium: indicates whether equilibrium calculations
                                    will be required in state blocks
            package_arguments: dict-like object of arguments to be passed to
                                state blocks as construction arguments
        Returns:
            None
        """
        if has_phase_equilibrium is None:
            raise ConfigurationError(
                    "{} add_state_blocks method was not provided with a "
                    "has_phase_equilibrium argument.".format(self.name))
        elif has_phase_equilibrium not in [True, False]:
            raise ConfigurationError(
                    "{} add_state_blocks method was provided with an invalid "
                    "has_phase_equilibrium argument. Must be True or False"
                    .format(self.name))

        tmp_dict = dict(**self.config.property_package_args)
        tmp_dict["has_phase_equilibrium"] = has_phase_equilibrium
        tmp_dict["parameters"] = self.config.property_package

        if information_flow == FlowDirection.forward:
            tmp_dict["defined_state"] = True
        elif information_flow == FlowDirection.backward:
            tmp_dict["defined_state"] = False
        else:
            raise ConfigurationError(
                    '{} invalid value for information_flow argument. '
                    'Valid values are FlowDirection.forward and '
                    'FlowDirection.backward'.format(self.name))

        try:
            self.properties_in = (
                    self.config.property_package.state_block_class(
                            self.flowsheet().config.time,
                            doc="Material properties at inlet",
                            default=tmp_dict))

            # Reverse defined_state
            tmp_dict_2 = dict(**tmp_dict)
            tmp_dict_2["defined_state"] = not tmp_dict["defined_state"]

            self.properties_out = (
                    self.config.property_package.state_block_class(
                            self.flowsheet().config.time,
                            doc="Material properties at outlet",
                            default=tmp_dict_2))
        except AttributeError:
            raise PropertyPackageError(
                    "{} physical property package has not implemented the "
                    "state_block_class attribute. Please contact the "
                    "developer of the physical property package."
                    .format(self.name))

    def add_reaction_blocks(self, has_equilibrium=None):
        """
        This method constructs the reaction block for the control volume.

        Args:
            has_equilibrium: indicates whether equilibrium calculations
                              will be required in reaction block
            package_arguments: dict-like object of arguments to be passed to
                                reaction block as construction arguments

        Returns:
            None
        """
        if has_equilibrium is None:
            raise ConfigurationError(
                    "{} add_reaction_blocks method was not provided with a "
                    "has_equilibrium argument.".format(self.name))
        elif has_equilibrium not in [True, False]:
            raise ConfigurationError(
                    "{} add_reaction_blocks method was provided with an "
                    "invalid has_equilibrium argument. Must be True or False"
                    .format(self.name))

        tmp_dict = dict(**self.config.reaction_package_args)
        tmp_dict["state_block"] = self.properties_out
        tmp_dict["has_equilibrium"] = has_equilibrium
        tmp_dict["parameters"] = self.config.reaction_package

        try:
            self.reactions = (
                    self.config.reaction_package.reaction_block_class(
                            self.flowsheet().config.time,
                            doc="Reaction properties in control volume",
                            default=tmp_dict))
        except AttributeError:
            raise PropertyPackageError(
                    "{} reaction property package has not implemented the "
                    "reaction_block_class attribute. Please contact the "
                    "developer of the reaction property package."
                    .format(self.name))

    def _add_material_balance_common(self,
                                     balance_type,
                                     has_rate_reactions,
                                     has_equilibrium_reactions,
                                     has_phase_equilibrium,
                                     has_mass_transfer,
                                     custom_molar_term,
                                     custom_mass_term):
        # Get dynamic and holdup flags from config block
        dynamic = self.config.dynamic
        has_holdup = self.config.has_holdup

        # Check that reaction block exists if required
        if has_rate_reactions or has_equilibrium_reactions:
            try:
                rblock = self.reactions
            except AttributeError:
                raise ConfigurationError(
                        "{} does not contain a Reaction Block, but material "
                        "balances have been set to contain reaction terms. "
                        "Please construct a reaction block before adding "
                        "balance equations.".format(self.name))

        if has_equilibrium_reactions:
            # Check that reaction block is set to calculate equilibrium
            for t in self.flowsheet().config.time:
                if self.reactions[t].config.has_equilibrium is False:
                    raise ConfigurationError(
                            "{} material balance was set to include "
                            "equilibrium reactions, however the associated "
                            "ReactionBlock was not set to include equilibrium "
                            "constraints (has_equilibrium_reactions=False). "
                            "Please correct your configuration arguments."
                            .format(self.name))

        if has_phase_equilibrium:
            # Check that state blocks are set to calculate equilibrium
            for t in self.flowsheet().config.time:
                if not self.properties_out[t].config.has_phase_equilibrium:
                    raise ConfigurationError(
                            "{} material balance was set to include phase "
                            "equilibrium, however the associated outlet "
                            "StateBlock was not set to include equilibrium "
                            "constraints (has_phase_equilibrium=False). Please"
                            " correct your configuration arguments."
                            .format(self.name))
                if not self.properties_in[t].config.has_phase_equilibrium:
                    raise ConfigurationError(
                            "{} material balance was set to include phase "
                            "equilibrium, however the associated inlet "
                            "StateBlock was not set to include equilibrium "
                            "constraints (has_phase_equilibrium=False). Please"
                            " correct your configuration arguments."
                            .format(self.name))

        # Get units from property package
        units = {}
        for u in ['length', 'holdup', 'amount', 'time']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Test for components that must exist prior to calling this method
        if has_holdup:
            if not hasattr(self, "volume"):
                raise ConfigurationError(
                        "{} control volume must have volume defined to have "
                        "holdup and/or rate reaction terms. Please call the "
                        "add_geometry method before adding balance equations."
                        .format(self.name))

        # Get phase component set and lists
        pc_set = self.config.property_package.get_phase_component_set()

        # Material holdup and accumulation
        if has_holdup:
            self.material_holdup = Var(self.flowsheet().config.time,
                                       pc_set,
                                       domain=Reals,
                                       initialize=1.0,
                                       doc="Material holdup in unit [{}]"
                                           .format(units['holdup']))
        if dynamic:
            self.material_accumulation = DerivativeVar(
                    self.material_holdup,
                    wrt=self.flowsheet().config.time,
                    doc="Material accumulation in unit [{}/{}]"
                        .format(units['holdup'], units['time']))

        # Create material balance terms as required
        # Kinetic reaction generation
        if has_rate_reactions:
            if not hasattr(self.config.reaction_package, "rate_reaction_idx"):
                raise PropertyNotSupportedError(
                    "{} Reaction package does not contain a list of rate "
                    "reactions (rate_reaction_idx), thus does not support "
                    "rate-based reactions.".format(self.name))
            self.rate_reaction_generation = Var(
                        self.flowsheet().config.time,
                        pc_set,
                        domain=Reals,
                        initialize=0.0,
                        doc="Amount of component generated in "
                            "unit by kinetic reactions [{}/{}]"
                            .format(units['holdup'], units['time']))

        # Equilibrium reaction generation
        if has_equilibrium_reactions:
            if not hasattr(self.config.reaction_package,
                           "equilibrium_reaction_idx"):
                raise PropertyNotSupportedError(
                    "{} Reaction package does not contain a list of "
                    "equilibrium reactions (equilibrium_reaction_idx), thus "
                    "does not support equilibrium-based reactions."
                    .format(self.name))
            self.equilibrium_reaction_generation = Var(
                self.flowsheet().config.time,
                pc_set,
                domain=Reals,
                initialize=0.0,
                doc="Amount of component generated in unit "
                    "by equilibrium reactions [{}/{}]"
                    .format(units['holdup'], units['time']))

        # Phase equilibrium generation
        if has_phase_equilibrium and \
                balance_type == MaterialBalanceType.componentPhase:
            if not hasattr(self.config.property_package,
                           "phase_equilibrium_idx"):
                raise PropertyNotSupportedError(
                    "{} Property package does not contain a list of phase "
                    "equilibrium reactions (phase_equilibrium_idx), thus does "
                    "not support phase equilibrium.".format(self.name))
            self.phase_equilibrium_generation = Var(
                self.flowsheet().config.time,
                self.config.property_package.phase_equilibrium_idx,
                domain=Reals,
                initialize=0.0,
                doc="Amount of generation in unit by phase "
                    "equilibria [{}/{}]"
                    .format(units['holdup'], units['time']))

        # Material transfer term
        if has_mass_transfer:
            self.mass_transfer_term = Var(
                        self.flowsheet().config.time,
                        pc_set,
                        domain=Reals,
                        initialize=0.0,
                        doc="Component material transfer into unit [{}/{}]"
                            .format(units['holdup'], units['time']))

        # Create rules to substitute material balance terms
        # Accumulation term
        def accumulation_term(b, t, p, j):
            return b.material_accumulation[t, p, j] if dynamic else 0

        def kinetic_term(b, t, p, j):
            return (b.rate_reaction_generation[t, p, j] if has_rate_reactions
                    else 0)

        def equilibrium_term(b, t, p, j):
            return (b.equilibrium_reaction_generation[t, p, j]
                    if has_equilibrium_reactions else 0)

        def phase_equilibrium_term(b, t, p, j):
            if has_phase_equilibrium and \
                    balance_type == MaterialBalanceType.componentPhase:
                sd = {}
                for r in b.config.property_package.phase_equilibrium_idx:
                    if b.config.property_package.\
                            phase_equilibrium_list[r][0] == j:
                        if b.config.property_package.\
                                phase_equilibrium_list[r][1][0] == p:
                            sd[r] = 1
                        elif b.config.property_package.\
                                phase_equilibrium_list[r][1][1] == p:
                            sd[r] = -1
                        else:
                            sd[r] = 0
                    else:
                        sd[r] = 0

                return sum(b.phase_equilibrium_generation[t, r] * sd[r]
                           for r in b.config.property_package.
                           phase_equilibrium_idx)
            else:
                return 0

        def transfer_term(b, t, p, j):
            return (b.mass_transfer_term[t, p, j] if has_mass_transfer else 0)

        # TODO: Need to set material_holdup = 0 for non-present component-phase
        # pairs. Not ideal, but needed to close DoF. Is there a better way?

        # Material Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             pc_set,
                             doc="Material holdup calculations")
            def material_holdup_calculation(b, t, p, j):
                if (p, j) in pc_set:
                    return b.material_holdup[t, p, j] == (
                          b.volume[t]*self.phase_fraction[t, p] *
                          b.properties_out[t].get_material_density_terms(p, j))

        if has_rate_reactions:
            # Add extents of reaction and stoichiometric constraints
            self.rate_reaction_extent = Var(
                    self.flowsheet().config.time,
                    self.config.reaction_package.rate_reaction_idx,
                    domain=Reals,
                    initialize=0.0,
                    doc="Extent of kinetic reactions[{}/{}]"
                        .format(units['holdup'], units['time']))

            @self.Constraint(self.flowsheet().config.time,
                             pc_set,
                             doc="Kinetic reaction stoichiometry constraint")
            def rate_reaction_stoichiometry_constraint(b, t, p, j):
                if (p, j) in pc_set:
                    rparam = rblock[t]._params
                    return b.rate_reaction_generation[t, p, j] == (
                        sum(rparam.rate_reaction_stoichiometry[r, p, j] *
                            b.rate_reaction_extent[t, r]
                            for r in b.config.reaction_package.
                            rate_reaction_idx))
                else:
                    return Constraint.Skip

        if has_equilibrium_reactions:
            # Add extents of reaction and stoichiometric constraints
            self.equilibrium_reaction_extent = Var(
                    self.flowsheet().config.time,
                    self.config.reaction_package.equilibrium_reaction_idx,
                    domain=Reals,
                    initialize=0.0,
                    doc="Extent of equilibrium reactions[{}/{}]"
                        .format(units['holdup'], units['time']))

            @self.Constraint(self.flowsheet().config.time,
                             pc_set,
                             doc="Equilibrium reaction stoichiometry")
            def equilibrium_reaction_stoichiometry_constraint(b, t, p, j):
                if (p, j) in pc_set:
                    return b.equilibrium_reaction_generation[t, p, j] == (
                            sum(rblock[t]._params.
                                equilibrium_reaction_stoichiometry[r, p, j] *
                                b.equilibrium_reaction_extent[t, r]
                                for r in b.config.reaction_package.
                                equilibrium_reaction_idx))
                else:
                    return Constraint.Skip

        # Add custom terms and material balances
        if balance_type == MaterialBalanceType.componentPhase:
            def user_term_mol(b, t, p, j):
                if custom_molar_term is not None:
                    flow_basis = b.properties_out[t].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.molar:
                        return custom_molar_term(t, p, j)
                    elif flow_basis == MaterialFlowBasis.mass:
                        try:
                            return (custom_molar_term(t, p, j) *
                                    b.properties_out[t].mw[j])
                        except AttributeError:
                            raise PropertyNotSupportedError(
                                "{} property package does not support "
                                "molecular weight (mw), which is required for "
                                "using custom terms in material balances."
                                .format(self.name))
                    else:
                        raise ConfigurationError(
                            "{} contained a custom_molar_term argument, but "
                            "the property package used an undefined basis "
                            "(MaterialFlowBasis.other). Custom terms can "
                            "only be used when the property package declares "
                            "a molar or mass flow basis.".format(self.name))
                else:
                    return 0

            def user_term_mass(b, t, p, j):
                if custom_mass_term is not None:
                    flow_basis = b.properties_out[t].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.mass:
                        return custom_mass_term(t, p, j)
                    elif flow_basis == MaterialFlowBasis.molar:
                        try:
                            return (custom_mass_term(t, p, j) /
                                    b.properties_out[t].mw[j])
                        except AttributeError:
                            raise PropertyNotSupportedError(
                                "{} property package does not support "
                                "molecular weight (mw), which is required for "
                                "using custom terms in material balances."
                                .format(self.name))
                    else:
                        raise ConfigurationError(
                            "{} contained a custom_mass_term argument, but "
                            "the property package used an undefined basis "
                            "(MaterialFlowBasis.other). Custom terms can "
                            "only be used when the property package declares "
                            "a molar or mass flow basis.".format(self.name))
                else:
                    return 0

            @self.Constraint(self.flowsheet().config.time,
                             pc_set,
                             doc="Material balances")
            def material_balances(b, t, p, j):
                if (p, j) in pc_set:
                    return accumulation_term(b, t, p, j) == (
                            b.properties_in[t].get_material_flow_terms(p, j) -
                            b.properties_out[t].get_material_flow_terms(p, j) +
                            kinetic_term(b, t, p, j) *
                            b._rxn_rate_conv(t, j, has_rate_reactions) +
                            equilibrium_term(b, t, p, j) +
                            phase_equilibrium_term(b, t, p, j) +
                            transfer_term(b, t, p, j) +
                            user_term_mol(b, t, p, j) +
                            user_term_mass(b, t, p, j))
                else:
                    return Constraint.Skip

        elif balance_type == MaterialBalanceType.componentTotal:
            def user_term_mol(b, t, j):
                if custom_molar_term is not None:
                    flow_basis = b.properties_out[t].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.molar:
                        return custom_molar_term(t, j)
                    elif flow_basis == MaterialFlowBasis.mass:
                        try:
                            return (custom_molar_term(t, j) *
                                    b.properties_out[t].mw[j])
                        except AttributeError:
                            raise PropertyNotSupportedError(
                                "{} property package does not support "
                                "molecular weight (mw), which is required for "
                                "using custom terms in material balances."
                                .format(self.name))
                    else:
                        raise ConfigurationError(
                            "{} contained a custom_molar_term argument, but "
                            "the property package used an undefined basis "
                            "(MaterialFlowBasis.other). Custom terms can "
                            "only be used when the property package declares "
                            "a molar or mass flow basis.".format(self.name))
                else:
                    return 0

            def user_term_mass(b, t, j):
                if custom_mass_term is not None:
                    flow_basis = b.properties_out[t].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.mass:
                        return custom_mass_term(t, j)
                    elif flow_basis == MaterialFlowBasis.molar:
                        try:
                            return (custom_mass_term(t, j) /
                                    b.properties_out[t].mw[j])
                        except AttributeError:
                            raise PropertyNotSupportedError(
                                "{} property package does not support "
                                "molecular weight (mw), which is required for "
                                "using custom terms in material balances."
                                .format(self.name))
                    else:
                        raise ConfigurationError(
                            "{} contained a custom_mass_term argument, but "
                            "the property package used an undefined basis "
                            "(MaterialFlowBasis.other). Custom terms can "
                            "only be used when the property package declares "
                            "a molar or mass flow basis.".format(self.name))
                else:
                    return 0

            @self.Constraint(self.flowsheet().config.time,
                             self.config.property_package.component_list,
                             doc="Material balances")
            def material_balances(b, t, j):
                cplist = []
                for p in self.config.property_package.phase_list:
                    if (p, j) in pc_set:
                        cplist.append(p)
                return (
                    sum(accumulation_term(b, t, p, j) for p in cplist) ==
                    sum(b.properties_in[t].get_material_flow_terms(p, j)
                        for p in cplist) -
                    sum(b.properties_out[t].get_material_flow_terms(p, j)
                        for p in cplist) +
                    sum(kinetic_term(b, t, p, j) for p in cplist) *
                    b._rxn_rate_conv(t, j, has_rate_reactions) +
                    sum(equilibrium_term(b, t, p, j) for p in cplist) +
                    sum(transfer_term(b, t, p, j) for p in cplist) +
                    user_term_mol(b, t, j) + user_term_mass(b, t, j))
        else:
            raise BurntToast()

        return self.material_balances

    def add_phase_component_balances(self,
                                     has_rate_reactions=False,
                                     has_equilibrium_reactions=False,
                                     has_phase_equilibrium=False,
                                     has_mass_transfer=False,
                                     custom_molar_term=None,
                                     custom_mass_term=None):
        """
        This method constructs a set of 0D material balances indexed by time,
        phase and component.

        Args:
            has_rate_reactions: whether default generation terms for rate
                    reactions should be included in material balances
            has_equilibrium_reactions: whether generation terms should for
                    chemical equilibrium reactions should be included in
                    material balances
            has_phase_equilibrium: whether generation terms should for phase
                    equilibrium behaviour should be included in material
                    balances
            has_mass_transfer: whether generic mass transfer terms should be
                    included in material balances
            custom_molar_term: a Pyomo Expression representing custom terms to
                    be included in material balances on a molar basis.
                    Expression must be indexed by time, phase list and
                    component list
            custom_mass_term: a Pyomo Expression representing custom terms to
                    be included in material balances on a mass basis.
                    Expression must be indexed by time, phase list and
                    component list

        Returns:
            Constraint object representing material balances
        """
        self._add_material_balance_common(
                balance_type=MaterialBalanceType.componentPhase,
                has_rate_reactions=has_rate_reactions,
                has_equilibrium_reactions=has_equilibrium_reactions,
                has_phase_equilibrium=has_phase_equilibrium,
                has_mass_transfer=has_mass_transfer,
                custom_molar_term=custom_molar_term,
                custom_mass_term=custom_mass_term)

        return self.material_balances

    def add_total_component_balances(self,
                                     has_rate_reactions=False,
                                     has_equilibrium_reactions=False,
                                     has_phase_equilibrium=False,
                                     has_mass_transfer=False,
                                     custom_molar_term=None,
                                     custom_mass_term=None):
        """
        This method constructs a set of 0D material balances indexed by time
        and component.

        Args:
            has_rate_reactions - whether default generation terms for rate
                    reactions should be included in material balances
            has_equilibrium_reactions - whether generation terms should for
                    chemical equilibrium reactions should be included in
                    material balances
            has_phase_equilibrium - whether generation terms should for phase
                    equilibrium behaviour should be included in material
                    balances
            has_mass_transfer - whether generic mass transfer terms should be
                    included in material balances
            custom_molar_term - a Pyomo Expression representing custom terms to
                    be included in material balances on a molar basis.
                    Expression must be indexed by time, phase list and
                    component list
            custom_mass_term - a Pyomo Expression representing custom terms to
                    be included in material balances on a mass basis.
                    Expression must be indexed by time, phase list and
                    component list

        Returns:
            Constraint object representing material balances
        """
        self._add_material_balance_common(
                balance_type=MaterialBalanceType.componentTotal,
                has_rate_reactions=has_rate_reactions,
                has_equilibrium_reactions=has_equilibrium_reactions,
                has_phase_equilibrium=has_phase_equilibrium,
                has_mass_transfer=has_mass_transfer,
                custom_molar_term=custom_molar_term,
                custom_mass_term=custom_mass_term)

        return self.material_balances

    def add_total_element_balances(self,
                                   has_rate_reactions=False,
                                   has_equilibrium_reactions=False,
                                   has_phase_equilibrium=False,
                                   has_mass_transfer=False,
                                   custom_elemental_term=None):
        """
        This method constructs a set of 0D element balances indexed by time.

        Args:
            has_rate_reactions - whether default generation terms for rate
                    reactions should be included in material balances
            has_equilibrium_reactions - whether generation terms should for
                    chemical equilibrium reactions should be included in
                    material balances
            has_phase_equilibrium - whether generation terms should for phase
                    equilibrium behaviour should be included in material
                    balances
            has_mass_transfer - whether generic mass transfer terms should be
                    included in material balances
            custom_elemental_term - a Pyomo Expression representing custom
                    terms to be included in material balances on a molar
                    elemental basis. Expression must be indexed by time and
                    element list

        Returns:
            Constraint object representing material balances
        """
        # Get dynamic and holdup flags from config block
        dynamic = self.config.dynamic
        has_holdup = self.config.has_holdup

        # Check that property package supports element balances
        if not hasattr(self.config.property_package, "element_list"):
            raise PropertyNotSupportedError(
                "{} property package provided does not contain a list of "
                "elements (element_list), and thus does not support "
                "elemental material balances. Please choose another type "
                "of material balance or a property package which supports "
                "elemental balances.")
        # Check for valid arguments to write total elemental balance
        if has_rate_reactions:
            raise ConfigurationError(
                "{} add_total_element_balances method provided with "
                "argument has_rate_reactions = True. Total element "
                "balances do not support rate based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        if has_equilibrium_reactions:
            raise ConfigurationError(
                "{} add_total_element_balances method provided with "
                "argument has_equilibrium_reactions = True. Total element "
                "balances do not support equilibrium based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        if has_phase_equilibrium:
            raise ConfigurationError(
                "{} add_total_element_balances method provided with "
                "argument has_phase_equilibrium = True. Total element "
                "balances do not support equilibrium based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        # Test for components that must exist prior to calling this method
        if has_holdup:
            if not hasattr(self, "volume"):
                raise ConfigurationError(
                        "{} control volume must have volume defined to have "
                        "holdup terms. Please call the "
                        "add_geometry method before adding balance equations."
                        .format(self.name))

        # Get units from property package
        units = {}
        for u in ['amount', 'time']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Add Material Balance terms
        if has_holdup:
            self.element_holdup = Var(
                    self.flowsheet().config.time,
                    self.config.property_package.element_list,
                    domain=Reals,
                    initialize=1.0,
                    doc="Elemental holdup in unit [{}]"
                        .format(units['amount']))

        if dynamic:
            self.element_accumulation = DerivativeVar(
                    self.element_holdup,
                    wrt=self.flowsheet().config.time,
                    doc="Elemental accumulation in unit [{}/{}]"
                        .format(units['amount'], units['time']))

        @self.Expression(self.flowsheet().config.time,
                         self.config.property_package.phase_list,
                         self.config.property_package.element_list,
                         doc="Inlet elemental flow terms [{}/{}]"
                             .format(units['amount'], units['time']))
        def elemental_flow_in(b, t, p, e):
            return sum(b.properties_in[t].get_material_flow_terms(p, j) *
                       b.properties_out[t]._params.element_comp[j][e]
                       for j in b.config.property_package.component_list)

        @self.Expression(self.flowsheet().config.time,
                         self.config.property_package.phase_list,
                         self.config.property_package.element_list,
                         doc="Outlet elemental flow terms [{}/{}]"
                             .format(units['amount'], units['time']))
        def elemental_flow_out(b, t, p, e):
            return sum(b.properties_out[t].get_material_flow_terms(p, j) *
                       b.properties_out[t]._params.element_comp[j][e]
                       for j in b.config.property_package.component_list)

        # Create material balance terms as needed
        if has_mass_transfer:
            self.elemental_mass_transfer_term = Var(
                            self.flowsheet().config.time,
                            self.config.property_package.element_list,
                            domain=Reals,
                            initialize=0.0,
                            doc="Element material transfer into unit [{}/{}]"
                            .format(units['amount'], units['time']))

        # Create rules to substitute material balance terms
        # Accumulation term
        def accumulation_term(b, t, e):
            return b.element_accumulation[t, e] if dynamic else 0

        # Mass transfer term
        def transfer_term(b, t, e):
            return (b.elemental_mass_transfer_term[t, e]
                    if has_mass_transfer else 0)

        # Custom term
        def user_term(t, e):
            if custom_elemental_term is not None:
                return custom_elemental_term(t, e)
            else:
                return 0

        # Element balances
        @self.Constraint(self.flowsheet().config.time,
                         self.config.property_package.element_list,
                         doc="Elemental material balances")
        def element_balances(b, t, e):
            return accumulation_term(b, t, e) == (
                        sum(b.elemental_flow_in[t, p, e]
                            for p in b.config.property_package.phase_list) -
                        sum(b.elemental_flow_out[t, p, e]
                            for p in b.config.property_package.phase_list) +
                        transfer_term(b, t, e) +
                        user_term(t, e))

        # Elemental Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             self.config.property_package.element_list,
                             doc="Elemental holdup calculation")
            def elemental_holdup_calculation(b, t, e):
                return b.element_holdup[t, e] == (
                    b.volume[t] *
                    sum(b.phase_fraction[t, p] *
                        b.properties_out[t].get_material_density_terms(p, j) *
                        b.properties_out[t]
                        ._params.element_comp[j][e]
                        for p in b.config.property_package.phase_list
                        for j in b.config.property_package.component_list))

        return self.element_balances

    def add_total_material_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_total_material_balances (yet)."
                .format(self.name))

    def add_total_enthalpy_balances(self,
                                    has_heat_of_reaction=False,
                                    has_heat_transfer=False,
                                    has_work_transfer=False,
                                    custom_term=None):
        """
        This method constructs a set of 0D enthalpy balances indexed by time
        and phase.

        Args:
            has_heat_of_reaction - whether terms for heat of reaction should
                    be included in enthalpy balance
            has_heat_transfer - whether terms for heat transfer should be
                    included in enthalpy balances
            has_work_transfer - whether terms for work transfer should be
                    included in enthalpy balances
            custom_term - a Pyomo Expression representing custom terms to
                    be included in enthalpy balances.
                    Expression must be indexed by time and phase list

        Returns:
            Constraint object representing enthalpy balances
        """
        # Get dynamic and holdup flags from config block
        dynamic = self.config.dynamic
        has_holdup = self.config.has_holdup

        # Test for components that must exist prior to calling this method
        if has_holdup:
            if not hasattr(self, "volume"):
                raise ConfigurationError(
                        "{} control volume must have volume defined to have "
                        "holdup terms. Please call the "
                        "add_geometry method before adding balance equations."
                        .format(self.name))
        if has_heat_of_reaction:
            if not (hasattr(self, "rate_reaction_extent") or
                    hasattr(self, "equilibrium_reaction_extent")):
                raise ConfigurationError(
                        "{} extent of reaction terms must exist in order to "
                        "have heat of reaction terms. Please ensure that "
                        "add_material_balance (or equivalent) is called before"
                        " adding energy balances.".format(self.name))

        # Get units from property package
        units = {}
        for u in ['energy', 'time']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Create variables
        if has_holdup:
            self.energy_holdup = Var(
                        self.flowsheet().config.time,
                        self.config.property_package.phase_list,
                        domain=Reals,
                        initialize=1.0,
                        doc="Energy holdup in unit [{}]"
                        .format(units['energy']))

        if dynamic is True:
            self.energy_accumulation = DerivativeVar(
                        self.energy_holdup,
                        wrt=self.flowsheet().config.time,
                        doc="Enthaly holdup in unit [{}/{}]"
                        .format(units['energy'], units['time']))

        # Create scaling factor
        self.scaling_factor_energy = Param(
                        default=1e-6,
                        mutable=True,
                        doc='Energy balance scaling parameter')

        # Create energy balance terms as needed
        # Heat transfer term
        if has_heat_transfer:
            self.heat = Var(self.flowsheet().config.time,
                            domain=Reals,
                            initialize=0.0,
                            doc="Heat transfered in unit [{}/{}]"
                                .format(units['energy'], units['time']))

        # Work transfer
        if has_work_transfer:
            self.work = Var(self.flowsheet().config.time,
                            domain=Reals,
                            initialize=0.0,
                            doc="Work transfered in unit [{}/{}]"
                                .format(units['energy'], units['time']))

        # Heat of Reaction
        if has_heat_of_reaction:
            @self.Expression(self.flowsheet().config.time,
                             doc="Heat of reaction term [{}/{}]"
                                 .format(units['energy'], units['time']))
            def heat_of_reaction(b, t):
                if hasattr(self, "rate_reaction_extent"):
                    rate_heat = -sum(b.rate_reaction_extent[t, r] *
                                     b.reactions[t].dh_rxn[r]
                                     for r in self.config.reaction_package.
                                     rate_reaction_idx)
                else:
                    rate_heat = 0

                if hasattr(self, "equilibrium_reaction_extent"):
                    equil_heat = -sum(
                            b.equilibrium_reaction_extent[t, e] *
                            b.reactions[t].dh_rxn[e]
                            for e in self.config.reaction_package.
                            equilibrium_reaction_idx)
                else:
                    equil_heat = 0

                return rate_heat + equil_heat

        # Create rules to substitute energy balance terms
        # Accumulation term
        def accumulation_term(b, t, p):
            return b.energy_accumulation[t, p] if dynamic else 0

        def heat_term(b, t):
            return b.heat[t] if has_heat_transfer else 0

        def work_term(b, t):
            return b.work[t] if has_work_transfer else 0

        def rxn_heat_term(b, t):
            return b.heat_of_reaction[t] if has_heat_of_reaction else 0

        # Custom term
        def user_term(t):
            if custom_term is not None:
                return custom_term(t)
            else:
                return 0

        # Energy balance equation
        @self.Constraint(self.flowsheet().config.time, doc="Energy balances")
        def enthalpy_balances(b, t):
            return (sum(accumulation_term(b, t, p) for p in
                    b.config.property_package.phase_list) *
                    b.scaling_factor_energy) == (
                        sum(b.properties_in[t].get_enthalpy_flow_terms(p)
                            for p in b.config.property_package.phase_list) *
                        b.scaling_factor_energy -
                        sum(self.properties_out[t].get_enthalpy_flow_terms(p)
                            for p in b.config.property_package.phase_list) *
                        b.scaling_factor_energy +
                        heat_term(b, t)*b.scaling_factor_energy +
                        work_term(b, t)*b.scaling_factor_energy +
                        rxn_heat_term(b, t)*b.scaling_factor_energy +
                        user_term(t)*b.scaling_factor_energy)

        # Energy Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             self.config.property_package.phase_list,
                             doc="Enthalpy holdup constraint")
            def enthalpy_holdup_calculation(b, t, p):
                return b.energy_holdup[t, p] == (
                            b.volume[t]*self.phase_fraction[t, p] *
                            b.properties_out[t].get_energy_density_terms(p))

        return self.enthalpy_balances

    def add_phase_enthalpy_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_phase_enthalpy_balances."
                .format(self.name))

    def add_phase_energy_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_phase_energy_balances."
                .format(self.name))

    def add_total_energy_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_total_energy_balances."
                .format(self.name))

    def add_total_pressure_balances(self,
                                    has_pressure_change=False,
                                    custom_term=None):
        """
        This method constructs a set of 0D pressure balances indexed by time.

        Args:
            has_pressure_change - whether terms for pressure change should be
                    included in enthalpy balances
            custom_term - a Pyomo Expression representing custom terms to
                    be included in pressure balances.
                    Expression must be indexed by time

        Returns:
            Constraint object representing pressure balances
        """
        # Get units from property package
        try:
            p_units = (self.config.property_package.get_metadata().
                       default_units['pressure'])
        except KeyError:
            p_units = '-'

        # Add Momentum Balance Variables as necessary
        if has_pressure_change:
            self.deltaP = Var(self.flowsheet().config.time,
                              domain=Reals,
                              initialize=0.0,
                              doc="Pressure difference across unit [{}]"
                                  .format(p_units))

        # Create rules to substitute energy balance terms
        # Pressure change term
        def deltaP_term(b, t):
            return b.deltaP[t] if has_pressure_change else 0

        # Custom term
        def user_term(t):
            if custom_term is not None:
                return custom_term(t)
            else:
                return 0

        # Create scaling factor
        self.scaling_factor_pressure = Param(
                    default=1e-4,
                    mutable=True,
                    doc='Momentum balance scaling parameter')

        # Momentum balance equation
        @self.Constraint(self.flowsheet().config.time, doc='Momentum balance')
        def pressure_balance(b, t):
            return 0 == (b.properties_in[t].pressure *
                         b.scaling_factor_pressure -
                         b.properties_out[t].pressure *
                         b.scaling_factor_pressure +
                         deltaP_term(b, t)*b.scaling_factor_pressure +
                         user_term(t)*b.scaling_factor_pressure)

        return self.pressure_balance

    def add_phase_pressure_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_phase_pressure_balances."
                .format(self.name))

    def add_phase_momentum_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_phase_momentum_balances."
                .format(self.name))

    def add_total_momentum_balances(self, *args, **kwargs):
        raise BalanceTypeNotSupportedError(
                "{} OD control volumes do not support "
                "add_total_momentum_balances."
                .format(self.name))

    def model_check(blk):
        """
        This method executes the model_check methods on the associated state
        blocks (if they exist). This method is generally called by a unit model
        as part of the unit's model_check method.

        Args:
            None

        Returns:
            None
        """
        # Try property block model check
        for t in blk.flowsheet().config.time:
            try:
                blk.properties_in[t].model_check()
            except AttributeError:
                _log.warning('{} ControlVolume inlet property block has no '
                             'model checks. To correct this, add a model_check'
                             ' method to the associated StateBlock class.'
                             .format(blk.name))
            try:
                blk.properties_out[t].model_check()
            except AttributeError:
                _log.warning('{} ControlVolume outlet property block has no '
                             'model checks. To correct this, add a '
                             'model_check method to the associated '
                             'StateBlock class.'.format(blk.name))

            try:
                blk.reactions[t].model_check()
            except AttributeError:
                _log.warning('{} ControlVolume outlet reaction block has no '
                             'model check. To correct this, add a '
                             'model_check method to the associated '
                             'ReactionBlock class.'.format(blk.name))

    def initialize(blk, state_args=None, outlvl=idaeslog.NOTSET, optarg=None,
                   solver='ipopt', hold_state=True):
        '''
        Initialization routine for 0D control volume (default solver ipopt)

        Keyword Arguments:
            state_args : a dict of arguments to be passed to the property
                         package(s) to provide an initial state for
                         initialization (see documentation of the specific
                         property package) (default = {}).
            outlvl : sets output log level of initialization routine
            optarg : solver options dictionary object (default=None)
            solver : str indicating whcih solver to use during
                     initialization (default = 'ipopt')
            hold_state : flag indicating whether the initialization routine
                     should unfix any state variables fixed during
                     initialization, **default** - True. **Valid values:**
                     **True** - states variables are not unfixed, and a dict of
                     returned containing flags for which states were fixed
                     during initialization, **False** - state variables are
                     unfixed after initialization by calling the release_state
                     method.

        Returns:
            If hold_states is True, returns a dict containing flags for which
            states were fixed during initialization.
        '''
        # Get inlet state if not provided
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="control_volume")
        if state_args is None:
            state_args = {}
            state_dict = (
                blk.properties_in[
                    blk.flowsheet().config.time.first()]
                .define_port_members())

            for k in state_dict.keys():
                if state_dict[k].is_indexed():
                    state_args[k] = {}
                    for m in state_dict[k].keys():
                        state_args[k][m] = state_dict[k][m].value
                else:
                    state_args[k] = state_dict[k].value

        # Initialize state blocks
        in_flags = blk.properties_in.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            hold_state=hold_state,
            state_args=state_args,
        )
        out_flags = blk.properties_out.initialize(
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            hold_state=True,
            state_args=state_args,
        )
        try:
            # TODO: setting state_vars_fixed may not work for heterogeneous
            # systems where a second control volume is involved, as we cannot
            # assume those state vars are also fixed. For now, heterogeneous
            # reactions should ignore the state_vars_fixed argument and always
            # check their state_vars.
            blk.reactions.initialize(
                outlvl=outlvl,
                optarg=optarg,
                solver=solver,
                state_vars_fixed=True,
            )
        except AttributeError:
            pass

        # Unfix outlet properties
        blk.properties_out.release_state(
            flags=out_flags,
            outlvl=outlvl,
        )
        init_log.info('Initialization Complete')
        return in_flags

    def release_state(blk, flags, outlvl=idaeslog.NOTSET):
        '''
        Method to release state variables fixed during initialization.

        Keyword Arguments:
            flags : dict containing information of which state variables
                    were fixed during initialization, and should now be
                    unfixed. This dict is returned by initialize if
                    hold_state = True.
            outlvl : sets output level of logging

        Returns:
            None
        '''
        blk.properties_in.release_state(flags, outlvl=outlvl)

    def _add_phase_fractions(self):
        """
        This method constructs the phase_fraction variables for the control
        volume, and the associated constraint on the sum of phase_fractions
        == 1. For systems with only one phase, phase_fraction is created as a
        Pyomo Expression with a value of 1.

        Args:
            None

        Returns:
            None
        """
        if len(self.config.property_package.phase_list) > 1:
            self.phase_fraction = Var(
                            self.flowsheet().config.time,
                            self.config.property_package.phase_list,
                            initialize=1 / len(self.config.
                                               property_package.phase_list),
                            doc='Volume fraction of holdup by phase')

            @self.Constraint(self.flowsheet().config.time,
                             doc='Sum of phase fractions == 1')
            def sum_of_phase_fractions(self, t):
                return 1 == sum(self.phase_fraction[t, p]
                                for p in self.config.
                                property_package.phase_list)
        else:
            @self.Expression(self.flowsheet().config.time,
                             self.config.property_package.phase_list,
                             doc='Volume fraction of holdup by phase')
            def phase_fraction(self, t, p):
                return 1

    def _rxn_rate_conv(b, t, j, has_rate_reactions):
        """
        Wrapper method for the _rxn_rate_conv method to hide the x argument
        required for 1D control volumes.
        """
        # Call the method in control_volume_base with x=None
        return super()._rxn_rate_conv(t, None, j, has_rate_reactions)

    def _get_performance_contents(self, time_point=0):
        """
        Collect all CV variables which are present to report.
        """
        var_dict = {}
        expr_dict = {}
        param_dict = {}

        time_only_vars = {"volume": "Volume",
                          "heat": "Heat Transfer",
                          "work": "Work Transfer",
                          "deltaP": "Pressure Change"}

        for v, n in time_only_vars.items():
            try:
                var_dict[n] = getattr(self, v)[time_point]
            except AttributeError:
                pass

        p_vars = {
            "phase_fraction": "Phase Fraction",
            "energy_holdup": "Energy Holdup",
            "energy_accumulation": "Energy Accumulation"}

        for v, n in p_vars.items():
            try:
                var_obj = getattr(self, v)
                for p in self.config.property_package.phase_list:
                    var_dict[f"{n} [{p}]"] = var_obj[time_point, p]
            except AttributeError:
                pass

        pc_vars = {
            "material_holdup": "Material Holdup",
            "material_accumulation": "Material Accumulation",
            "rate_reaction_generation": "Rate Reaction Generation",
            "equilibrium_reaction_generation":
                "Equilibrium Reaction Generation",
            "mass_transfer_term": "Mass Transfer Term"}

        for v, n in pc_vars.items():
            try:
                var_obj = getattr(self, v)
                for p in self.config.property_package.phase_list:
                    for j in self.config.property_package.component_list:
                        var_dict[f"{n} [{p}, {j}]"] = \
                            var_obj[time_point, p, j]
            except AttributeError:
                pass

        if hasattr(self, "rate_reaction_extent"):
            for r in self.config.reaction_package.rate_reaction_idx:
                var_dict[f"Rate Reaction Extent [{r}]"] = \
                    self.rate_reaction_extent[time_point, r]
        if hasattr(self, "equilibrium_reaction_extent"):
            for r in self.config.reaction_package.equilibrium_reaction_idx:
                var_dict[f"Equilibrium Reaction Extent [{r}]"] = \
                    self.equilibrium_reaction_extent[time_point, r]
        if hasattr(self, "phase_equilibrium_generation"):
            for r in self.config.property_package.phase_equilibrium_idx:
                var_dict[f"Phase Equilibrium Generation [{r}]"] = \
                    self.phase_equilibrium_generation[time_point, r]

        e_vars = {
            "element_holdup": "Elemental Holdup",
            "element_accumulation": "Elemental Accumulation",
            "elemental_mass_transfer_term": "Elemental Transfer Term"}

        for v, n in e_vars.items():
            try:
                var_obj = getattr(self, v)
                for e in self.config.property_package.element_list:
                    var_dict[f"{n} [{e}]"] = var_obj[time_point, e]
            except AttributeError:
                pass

        time_only_exprs = {"heat_of_reaction": "Heat of Reaction Term"}

        for e, n in time_only_exprs.items():
            try:
                expr_dict[n] = getattr(self, e)[time_point]
            except AttributeError:
                pass

        e_exprs = {"elemental_flow_in": "Element Flow In",
                   "elemental_flow_out": "Element Flow Out"}

        for o, n in e_exprs.items():
            try:
                expr_obj = getattr(self, o)
                for p in self.config.property_package.phase_list:
                    for e in self.config.property_package.element_list:
                        expr_dict[f"{n} [{p}, {e}]"] = \
                            expr_obj[time_point, p, e]
            except AttributeError:
                pass

        params = {"scaling_factor_energy": "Energy Scaling",
                  "scaling_factor_pressure": "Pressure Scaling"}

        for p, n in params.items():
            try:
                param_dict[n] = getattr(self, p)
            except AttributeError:
                pass

        return {"vars": var_dict,
                "exprs": expr_dict,
                "params": param_dict}

    def _get_stream_table_contents(self, time_point=0):
        """
        Assume unit has standard configuration of 1 inlet and 1 outlet.

        Developers should overload this as appropriate.
        """
        try:
            return create_stream_table_dataframe({"In": self.properties_in,
                                                  "Out": self.properties_out},
                                                 time_point=time_point)
        except AttributeError:
            return (f"Unit model {self.name} does not have the standard Port "
                    f"names (inet and outlet). Please contact the unit model "
                    f"developer to develop a unit specific stream table.")
