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

# Import Python libraries
import copy

# Import Pyomo libraries
from pyomo.environ import (Constraint,
                           Param,
                           Reals,
                           TransformationFactory,
                           Var)
from pyomo.dae import ContinuousSet, DerivativeVar
from pyomo.common.config import ConfigValue, In
from pyutilib.enum import Enum

# Import IDAES cores
from idaes.core import (declare_process_block_class,
                        ControlVolumeBlockData,
                        FlowDirection,
                        MaterialFlowBasis,
                        MaterialBalanceType)
from idaes.core.util.exceptions import (BalanceTypeNotSupportedError,
                                        ConfigurationError,
                                        PropertyNotSupportedError)
from idaes.core.util.misc import add_object_reference
from idaes.core.util.config import (is_transformation_method,
                                    is_transformation_scheme)
import idaes.logger as idaeslog

__author__ = "Andrew Lee, Jaffer Ghouse"


_log = idaeslog.getLogger(__name__)

# TODO : Custom terms in material balances, other types of material balances
# Diffusion terms need to be added


# Enumerate options for area
DistributedVars = Enum(
    'variant',
    'uniform')


@declare_process_block_class("ControlVolume1DBlock", doc="""
    ControlVolume1DBlock is a specialized Pyomo block for IDAES control volume
    blocks discretized in one spatial direction, and contains instances of
    ControlVolume1DBlockData.

    ControlVolume1DBlock should be used for any control volume with a defined
    volume and distinct inlets and outlets where there is a single spatial
    domain parallel to the material flow direction. This encompases unit
    operations such as plug flow reactors and pipes.""")
class ControlVolume1DBlockData(ControlVolumeBlockData):
    """
    1-Dimensional ControlVolume Class

    This class forms the core of all 1-D IDAES models. It provides
    methods to build property and reaction blocks, and add mass, energy and
    momentum balances. The form of the terms used in these constraints is
    specified in the chosen property package.
    """
    CONFIG = ControlVolumeBlockData.CONFIG()
    CONFIG.declare("area_definition", ConfigValue(
        default=DistributedVars.uniform,
        domain=In(DistributedVars),
        description="Argument for defining form of area variable",
        doc="""Argument defining whether area variable should be spatially
        variant or not. **default** - DistributedVars.uniform.
        **Valid values:** {
        DistributedVars.uniform - area does not vary across spatial domian,
        DistributedVars.variant - area can vary over the domain and is indexed
        by time and space.}"""))
    CONFIG.declare("transformation_method", ConfigValue(
        default=None,
        domain=is_transformation_method,
        description="DAE transformation method",
        doc="""Method to use to transform domain. Must be a method recognised
by the Pyomo TransformationFactory."""))
    CONFIG.declare("transformation_scheme", ConfigValue(
        default=None,
        domain=is_transformation_scheme,
        description="DAE transformation scheme",
        doc="""Scheme to use when transformating domain. See Pyomo
documentation for supported schemes."""))
    CONFIG.declare("finite_elements", ConfigValue(
        default=None,
        domain=int,
        description="Number of finite elements",
        doc="""Number of finite elements to use in transformation (equivalent
to Pyomo nfe argument)."""))
    CONFIG.declare("collocation_points", ConfigValue(
        default=None,
        domain=int,
        description="Number of collocation points",
        doc="""Number of collocation points to use (equivalent to Pyomo ncp
argument)."""))

    def build(self):
        """
        Build method for ControlVolume1DBlock blocks.

        Returns:
            None
        """
        # Call build method from base class
        super(ControlVolume1DBlockData, self).build()

        self._validate_config_args()

    def _validate_config_args(self):
        # Validate DAE config arguments
        if self.config.transformation_method is None:
            raise ConfigurationError(
                    "{} was not provided a value for the transformation_method"
                    " configuration argument. Please provide a valid value."
                    .format(self.name))

        if self.config.transformation_scheme is None:
            raise ConfigurationError(
                    "{} was not provided a value for the transformation_scheme"
                    " configuration argument. Please provide a valid value."
                    .format(self.name))
        elif ((self.config.transformation_method == "dae.finite_difference" and
              self.config.transformation_scheme not in ["BACKWARD", "FORWARD"])
                or (self.config.transformation_method == "dae.collocation" and
                    self.config.transformation_scheme not in
                    ["LAGRANGE-LEGENDRE", "LAGRANGE-RADAU"])):
            raise ConfigurationError(
                    "{} transformation_scheme configuration argument is not "
                    "consistent with transformation_method argument. See Pyomo"
                    " documentation for argument options."
                    .format(self.name))

    def add_geometry(self,
                     length_domain=None,
                     length_domain_set=[0.0, 1.0],
                     flow_direction=FlowDirection.forward):
        """
        Method to create spatial domain and volume Var in ControlVolume.

        Args:
            length_domain - (optional) a ContinuousSet to use as the length
                            domain for the ControlVolume. If not provided, a
                            new ContinuousSet will be created (default=None).
                            ContinuousSet should be normalized to run between
                            0 and 1.
            length_domain_set - (optional) list of point to use to initialize
                            a new ContinuousSet if length_domain is not
                            provided (default = [0.0, 1.0]).
            flow_direction - argument indicating direction of material flow
                            relative to length domain. Valid values:
                                - FlowDirection.forward (default), flow goes
                                  from 0 to 1.
                                - FlowDirection.backward, flow goes from 1 to 0

        Returns:
            None
        """
        l_units = self.config.property_package.get_metadata().default_units[
                                                                      "length"]

        if length_domain is not None:
            # Validate domain and make a reference
            if isinstance(length_domain, ContinuousSet):
                add_object_reference(self, "length_domain", length_domain)
            else:
                raise ConfigurationError(
                        "{} length_domain argument must be a Pyomo "
                        "ContinuousSet object".format(self.name))
        else:
            # Create new length domain
            self.length_domain = ContinuousSet(
                                    bounds=(0.0, 1.0),
                                    initialize=length_domain_set,
                                    doc="Normalized length domain")

        # Validated and create flow direction attribute
        if flow_direction in (flwd for flwd in FlowDirection):
            self._flow_direction = flow_direction
        else:
            raise ConfigurationError("{} invalid value for flow_direction "
                                     "argument. Must be a FlowDirection Enum."
                                     .format(self.name))
        if flow_direction is FlowDirection.forward:
            self._flow_direction_term = -1
        else:
            self._flow_direction_term = 1

        # Add geomerty variables and constraints
        if self.config.area_definition == DistributedVars.variant:
            self.area = Var(self.flowsheet().config.time,
                            self.length_domain,
                            initialize=1.0,
                            doc='Cross-sectional area of Control Volume [{}^2]'
                                .format(l_units))
        else:
            self.area = Var(initialize=1.0,
                            doc='Cross-sectional area of Control Volume [{}^2]'
                                .format(l_units))
        self.length = Var(initialize=1.0,
                          doc='Length of Control Volume [{}]'.format(l_units))

    def add_state_blocks(self,
                         information_flow=FlowDirection.forward,
                         has_phase_equilibrium=None):
        """
        This method constructs the state blocks for the
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

        # d0 is config for defined state d1 is config for not defined state
        d0 = dict(**self.config.property_package_args)
        d0.update(has_phase_equilibrium=has_phase_equilibrium,
                  parameters=self.config.property_package,
                  defined_state=True)
        d1 = copy.copy(d0)
        d1["defined_state"] = False

        def idx_map(i):  # i = (t, x)
            if information_flow == FlowDirection.forward and \
                    i[1] == self.length_domain.first():
                return 0
            elif information_flow == FlowDirection.backward and \
                    i[1] == self.length_domain.last():
                return 0
            else:
                return 1
        self.properties = self.config.property_package.state_block_class(
            self.flowsheet().config.time,
            self.length_domain,
            doc="Material properties",
            initialize={0: d0, 1: d1},                                          # TODO: What if the domain has different bounds?
            idx_map=idx_map)

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

        # TODO : Should not have ReactionBlock at inlet
        tmp_dict = dict(**self.config.reaction_package_args)
        tmp_dict["state_block"] = self.properties
        tmp_dict["has_equilibrium"] = has_equilibrium
        tmp_dict["parameters"] = self.config.reaction_package

        self.reactions = self.config.reaction_package.reaction_block_class(
                self.flowsheet().config.time,
                self.length_domain,
                doc="Reaction properties in control volume",
                default=tmp_dict)                                               # TODO: Do we need something similar to above to skip equilibrium at bounds?

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
                for x in self.length_domain:
                    if self.reactions[t, x].config.has_equilibrium is False:
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
                for x in self.length_domain:
                    if not self.properties[t, x].config.has_phase_equilibrium:
                        raise ConfigurationError(
                            "{} material balance was set to include phase "
                            "equilibrium, however the associated "
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

        # Get phase component set and lists
        pc_set = self.config.property_package.get_phase_component_set()

        # Material holdup and accumulation
        if has_holdup:
            self.material_holdup = Var(
                    self.flowsheet().config.time,
                    self.length_domain,
                    pc_set,
                    domain=Reals,
                    initialize=1.0,
                    doc="Material holdup per unit length [{}/{}]"
                        .format(units['holdup'], units['length']))
        if dynamic:
            self.material_accumulation = DerivativeVar(
                    self.material_holdup,
                    wrt=self.flowsheet().config.time,
                    doc="Material accumulation per unit length [{}/{}.{}]"
                        .format(units['holdup'],
                                units['length'],
                                units['time']))

        # Create material balance terms as required
        # Flow terms and derivatives
        self._flow_terms = Var(self.flowsheet().config.time,
                               self.length_domain,
                               pc_set,
                               initialize=1.0,
                               doc="Flow terms for material balance equations")

        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         pc_set,
                         doc="Material flow linking constraints")
        def material_flow_linking_constraints(b, t, x, p, j):
            return b._flow_terms[t, x, p, j] == \
                b.properties[t, x].get_material_flow_terms(p, j)

        self.material_flow_dx = DerivativeVar(
                                     self._flow_terms,
                                     wrt=self.length_domain,
                                     doc="Parital derivative of material flow "
                                         "wrt to length {}/{}.{}"
                                         .format(units['holdup'],
                                                 units['length'],
                                                 units['time']))

        # Kinetic reaction generation
        if has_rate_reactions:
            if not hasattr(self.config.reaction_package, "rate_reaction_idx"):
                raise PropertyNotSupportedError(
                    "{} Reaction package does not contain a list of rate "
                    "reactions (rate_reaction_idx), thus does not support "
                    "rate-based reactions.".format(self.name))
            self.rate_reaction_generation = Var(
                        self.flowsheet().config.time,
                        self.length_domain,
                        pc_set,
                        domain=Reals,
                        initialize=0.0,
                        doc="Amount of component generated in "
                            "by kinetic reactions per unit length [{}/{}.{}]"
                            .format(units['holdup'],
                                    units['length'],
                                    units['time']))

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
                self.length_domain,
                pc_set,
                domain=Reals,
                initialize=0.0,
                doc="Amount of component generated by equilibrium "
                    "reactions per unit length [{}/{}.{}]"
                    .format(units['holdup'],
                            units['length'],
                            units['time']))

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
                        self.length_domain,
                        self.config.property_package.phase_equilibrium_idx,
                        domain=Reals,
                        initialize=0.0,
                        doc="Amount of generation in unit by phase "
                            "equilibria per unit length [{}/{}.{}]"
                            .format(units['holdup'],
                                    units['length'],
                                    units['time']))

        # Material transfer term
        if has_mass_transfer:
            self.mass_transfer_term = Var(
                        self.flowsheet().config.time,
                        self.length_domain,
                        pc_set,
                        domain=Reals,
                        initialize=0.0,
                        doc="Component material transfer into unit per unit "
                            "length [{}/{}.{}]"
                            .format(units['holdup'],
                                    units['length'],
                                    units['time']))

        # Create rules to substitute material balance terms
        # Accumulation term
        def accumulation_term(b, t, x, p, j):
            return b.material_accumulation[t, x, p, j] if dynamic else 0

        def kinetic_term(b, t, x, p, j):
            return (b.rate_reaction_generation[t, x, p, j]
                    if has_rate_reactions else 0)

        def equilibrium_term(b, t, x, p, j):
            return (b.equilibrium_reaction_generation[t, x, p, j]
                    if has_equilibrium_reactions else 0)

        def phase_equilibrium_term(b, t, x, p, j):
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

                return sum(
                        b.phase_equilibrium_generation[t, x, r] * sd[r] for
                        r in b.config.property_package.phase_equilibrium_idx)
            else:
                return 0

        def transfer_term(b, t, x, p, j):
            return (b.mass_transfer_term[t, x, p, j]
                    if has_mass_transfer else 0)

        # TODO: Need to set material_holdup = 0 for non-present component-phase
        # pairs. Not ideal, but needed to close DoF. Is there a better way?

        # Material Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             pc_set,
                             doc="Material holdup calculations")
            def material_holdup_calculation(b, t, x, p, j):
                if (p, j) in pc_set:
                    return b.material_holdup[t, x, p, j] == (
                          b._area_func(t, x)*self.phase_fraction[t, x, p] *
                          b.properties[t, x].get_material_density_terms(p, j))

        if has_rate_reactions:
            # Add extents of reaction and stoichiometric constraints
            self.rate_reaction_extent = Var(
                    self.flowsheet().config.time,
                    self.length_domain,
                    self.config.reaction_package.rate_reaction_idx,
                    domain=Reals,
                    initialize=0.0,
                    doc="Extent of kinetic reactions at point x [{}/{}.{}]"
                        .format(units['holdup'],
                                units['length'],
                                units['time']))

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             pc_set,
                             doc="Kinetic reaction stoichiometry constraint")
            def rate_reaction_stoichiometry_constraint(b, t, x, p, j):
                if (p, j) in pc_set:
                    rparam = rblock[t, x].config.parameters
                    return b.rate_reaction_generation[t, x, p, j] == (
                        sum(rparam.rate_reaction_stoichiometry[r, p, j] *
                            b.rate_reaction_extent[t, x, r] for r in
                            b.config.reaction_package.rate_reaction_idx))
                else:
                    return Constraint.Skip

        if has_equilibrium_reactions:
            # Add extents of reaction and stoichiometric constraints
            self.equilibrium_reaction_extent = Var(
                self.flowsheet().config.time,
                self.length_domain,
                self.config.reaction_package.equilibrium_reaction_idx,
                domain=Reals,
                initialize=0.0,
                doc="Extent of equilibrium reactions at point x "
                    "[{}/{}.{}]".format(units['holdup'],
                                        units['length'],
                                        units['time']))

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             pc_set,
                             doc="Equilibrium reaction stoichiometry")
            def equilibrium_reaction_stoichiometry_constraint(b, t, x, p, j):
                if (p, j) in pc_set:
                    return b.equilibrium_reaction_generation[t, x, p, j] == (
                        sum(rblock[t, x].config.parameters.
                            equilibrium_reaction_stoichiometry[r, p, j] *
                            b.equilibrium_reaction_extent[t, x, r]
                            for r in b.config.reaction_package.
                            equilibrium_reaction_idx))
                else:
                    return Constraint.Skip

        # Add custom terms and material balances
        if balance_type == MaterialBalanceType.componentPhase:
            def user_term_mol(b, t, x, p, j):
                if custom_molar_term is not None:
                    flow_basis = b.properties[t, x].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.molar:
                        return custom_molar_term(t, x, p, j)
                    elif flow_basis == MaterialFlowBasis.mass:
                        try:
                            return (custom_molar_term(t, x, p, j) *
                                    b.properties[t, x].mw[j])
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

            def user_term_mass(b, t, x, p, j):
                if custom_mass_term is not None:
                    flow_basis = b.properties[t, x].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.mass:
                        return custom_mass_term(t, x, p, j)
                    elif flow_basis == MaterialFlowBasis.molar:
                        try:
                            return (custom_mass_term(t, x, p, j) /
                                    b.properties[t, x].mw[j])
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
                             self.length_domain,
                             pc_set,
                             doc="Material balances")
            def material_balances(b, t, x, p, j):
                if ((b.config.transformation_scheme != "FORWARD" and
                     x == b.length_domain.first()) or
                        (b.config.transformation_scheme == "FORWARD" and
                         x == b.length_domain.last())):
                    return Constraint.Skip
                else:
                    if (p, j) in pc_set:
                        return b.length*accumulation_term(b, t, x, p, j) == (
                            b._flow_direction_term *
                            b.material_flow_dx[t, x, p, j] +
                            b.length*kinetic_term(b, t, x, p, j) *
                            b._rxn_rate_conv(t, x, j, has_rate_reactions) +
                            b.length*equilibrium_term(b, t, x, p, j) +
                            b.length*phase_equilibrium_term(b, t, x, p, j) +
                            b.length*transfer_term(b, t, x, p, j) +
                            #b.area*diffusion_term(b, t, x, p, j)/b.length +
                            b.length*user_term_mol(b, t, x, p, j) +
                            b.length*user_term_mass(b, t, x, p, j))
                    else:
                        return Constraint.Skip

        elif balance_type == MaterialBalanceType.componentTotal:
            def user_term_mol(b, t, x, j):
                if custom_molar_term is not None:
                    flow_basis = b.properties[t, x].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.molar:
                        return custom_molar_term(t, x, j)
                    elif flow_basis == MaterialFlowBasis.mass:
                        try:
                            return (custom_molar_term(t, x, j) *
                                    b.properties[t, x].mw[j])
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

            def user_term_mass(b, t, x, j):
                if custom_mass_term is not None:
                    flow_basis = b.properties[t, x].get_material_flow_basis()
                    if flow_basis == MaterialFlowBasis.mass:
                        return custom_mass_term(t, x, j)
                    elif flow_basis == MaterialFlowBasis.molar:
                        try:
                            return (custom_mass_term(t, x, j) /
                                    b.properties[t, x].mw[j])
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

            # Add component balances
            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             self.config.property_package.component_list,
                             doc="Material balances")
            def material_balances(b, t, x, j):
                if ((b.config.transformation_scheme != "FORWARD" and
                     x == b.length_domain.first()) or
                        (b.config.transformation_scheme == "FORWARD" and
                         x == b.length_domain.last())):
                    return Constraint.Skip
                else:
                    cplist = []
                    for p in self.config.property_package.phase_list:
                        if (p, j) in pc_set:
                            cplist.append(p)
                    return (
                        b.length*sum(accumulation_term(b, t, x, p, j)
                                     for p in cplist) ==
                        b._flow_direction_term*sum(
                            b.material_flow_dx[t, x, p, j]
                            for p in cplist) +
                        b.length*sum(kinetic_term(b, t, x, p, j)
                                     for p in cplist) *
                        b._rxn_rate_conv(t, x, j, has_rate_reactions) +
                        b.length*sum(equilibrium_term(b, t, x, p, j)
                                     for p in cplist) +
                        b.length*sum(transfer_term(b, t, x, p, j)
                                     for p in cplist) +
                        b.length*user_term_mol(b, t, x, j) +
                        b.length*user_term_mass(b, t, x, j))

    def add_phase_component_balances(self,
                                     has_rate_reactions=False,
                                     has_equilibrium_reactions=False,
                                     has_phase_equilibrium=False,
                                     has_mass_transfer=False,
                                     custom_molar_term=None,
                                     custom_mass_term=None):
        """
        This method constructs a set of 1D material balances indexed by time,
        length, phase and component.

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
                    Expression must be indexed by time, length domain, phase
                    list and component list
            custom_mass_term: a Pyomo Expression representing custom terms to
                    be included in material balances on a mass basis.
                    Expression must be indexed by time, length domain, phase
                    list and component list

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
        This method constructs a set of 1D material balances indexed by time
        length and component.

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
                    Expression must be indexed by time, length domain and
                    component list
            custom_mass_term: a Pyomo Expression representing custom terms to
                    be included in material balances on a mass basis.
                    Expression must be indexed by time, length domain and
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
        This method constructs a set of 1D element balances indexed by time and
        length.

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
                    elemental basis. Expression must be indexed by time, length
                    and element list

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

        # Check validity of arguments to write the total elemental balance
        if has_rate_reactions:
            raise ConfigurationError(
                "{} add_total_element_balances method as provided with "
                "argument has_rate_reactions = True. Total element "
                "balances do not support rate based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        if has_equilibrium_reactions:
            raise ConfigurationError(
                "{} add_total_element_balances method as provided with "
                "argument has_equilibrium_reactions = True. Total element "
                "balances do not support equilibrium based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        if has_phase_equilibrium:
            # Check that state blocks are set to calculate equilibrium
            raise ConfigurationError(
                "{} add_total_element_balances method as provided with "
                "argument has_phase_equilibrium = True. Total element "
                "balances do not support equilibrium based reactions, "
                "please correct your configuration arguments"
                .format(self.name))

        # Get units from property package
        units = {}
        for u in ['amount', 'length', 'time']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Add Material Balance terms
        if has_holdup:
            self.element_holdup = Var(
                    self.flowsheet().config.time,
                    self.length_domain,
                    self.config.property_package.element_list,
                    domain=Reals,
                    initialize=1.0,
                    doc="Elemental holdup per unit length [{}/{}]"
                        .format(units['amount'], units['length']))

        if dynamic:
            self.element_accumulation = DerivativeVar(
                self.element_holdup,
                wrt=self.flowsheet().config.time,
                doc="Elemental accumulation per unit length [{}/{}.{}]"
                    .format(units['amount'],
                            units['length'],
                            units['time']))

        self.elemental_flow_term = Var(self.flowsheet().config.time,
                                       self.length_domain,
                                       self.config.property_package.
                                       element_list,
                                       initialize=1.0,
                                       doc="Elemental flow terms [{}/{}]"
                                           .format(units['amount'],
                                                   units['time']))

        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         self.config.property_package.element_list,
                         doc="Elemental flow constraints")
        def elemental_flow_constraint(b, t, x, e):
            return b.elemental_flow_term[t, x, e] == (
                sum(sum(b.properties[t, x].get_material_flow_terms(p, j) *
                        b.properties[t, x].config.parameters.element_comp[j][e]
                        for j in b.config.property_package.component_list)
                    for p in b.config.property_package.phase_list))

        self.elemental_flow_dx = DerivativeVar(self.elemental_flow_term,
                                               wrt=self.length_domain,
                                               doc="Partial derivative of "
                                               "elemental flow wrt length")

        # Create material balance terms as needed
        if has_mass_transfer:
            self.elemental_mass_transfer_term = Var(
                            self.flowsheet().config.time,
                            self.length_domain,
                            self.config.property_package.element_list,
                            domain=Reals,
                            initialize=0.0,
                            doc="Element material transfer into unit per unit "
                                "length [{}/{}.{}]"
                                .format(units['amount'],
                                        units['length'],
                                        units['time']))

        # Create rules to substitute material balance terms
        # Accumulation term
        def accumulation_term(b, t, x, e):
            return b.element_accumulation[t, x, e] if dynamic else 0

        # Mass transfer term
        def transfer_term(b, t, x, e):
            return (b.elemental_mass_transfer_term[t, x, e]
                    if has_mass_transfer else 0)

        # Custom term
        def user_term(t, x, e):
            if custom_elemental_term is not None:
                return custom_elemental_term(t, x, e)
            else:
                return 0

        # Element balances
        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         self.config.property_package.element_list,
                         doc="Elemental material balances")
        def element_balances(b, t, x, e):
            if ((b.config.transformation_scheme != "FORWARD" and
                 x == b.length_domain.first()) or
                    (b.config.transformation_scheme == "FORWARD" and
                     x == b.length_domain.last())):
                return Constraint.Skip
            else:
                return b.length * accumulation_term(b, t, x, e) == (
                    b._flow_direction_term *
                    b.elemental_flow_dx[t, x, e] +
                    b.length * transfer_term(b, t, x, e) +
                    b.length * user_term(t, x, e))  # +
                    # TODO : Add diffusion terms
                    #b.area*diffusion_term(b, t, x, e)/b.length)

        # Elemental Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             self.config.property_package.element_list,
                             doc="Elemental holdup calculation")
            def elemental_holdup_calculation(b, t, x, e):
                return b.element_holdup[t, x, e] == (
                    b._area_func(t, x) *
                    sum(b.phase_fraction[t, x, p] *
                        b.properties[t, x].get_material_density_terms(p, j) *
                        b.properties[t, x].config.parameters.element_comp[j][e]
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
        This method constructs a set of 1D enthalpy balances indexed by time
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
                    Expression must be indexed by time, length and phase list

        Returns:
            Constraint object representing enthalpy balances
        """
        # Get dynamic and holdup flags from config block
        dynamic = self.config.dynamic
        has_holdup = self.config.has_holdup

        # Test for components that must exist prior to calling this method
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
        for u in ['energy', 'length', 'time']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Create variables
        self._enthalpy_flow = Var(self.flowsheet().config.time,
                                  self.length_domain,
                                  self.config.property_package.phase_list,
                                  initialize=1.0,
                                  doc="Enthalpy flow terms")

        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         self.config.property_package.phase_list,
                         doc="Enthapy flow linking constraints")
        def enthalpy_flow_linking_constraint(b, t, x, p):
            return b._enthalpy_flow[t, x, p] == \
                    b.properties[t, x].get_enthalpy_flow_terms(p)

        self.enthalpy_flow_dx = DerivativeVar(self._enthalpy_flow,
                                              wrt=self.length_domain,
                                              doc="Partial derivative of "
                                              "enthalpy flow wrt length")

        if has_holdup:
            self.energy_holdup = Var(
                        self.flowsheet().config.time,
                        self.length_domain,
                        self.config.property_package.phase_list,
                        domain=Reals,
                        initialize=1.0,
                        doc="Enthalpy holdup per unit length [{}/{}]"
                        .format(units['energy'], units['length']))

        if dynamic is True:
            self.energy_accumulation = DerivativeVar(
                        self.energy_holdup,
                        wrt=self.flowsheet().config.time,
                        doc="Energy accumulation per unit length [{}/{}.{}]"
                        .format(units['energy'],
                                units['length'],
                                units['time']))

        # Create scaling factor
        self.scaling_factor_energy = Param(
                        default=1e-6,
                        mutable=True,
                        doc='Energy balance scaling parameter')

        # Create energy balance terms as needed
        # Heat transfer term
        if has_heat_transfer:
            self.heat = Var(self.flowsheet().config.time,
                            self.length_domain,
                            domain=Reals,
                            initialize=0.0,
                            doc="Heat transfered per unit length [{}/{}.{}]"
                                .format(units['energy'],
                                        units['length'],
                                        units['time']))

        # Work transfer
        if has_work_transfer:
            self.work = Var(self.flowsheet().config.time,
                            self.length_domain,
                            domain=Reals,
                            initialize=0.0,
                            doc="Work transfered per unit length [{}/{}.{}]"
                                .format(units['energy'],
                                        units['length'],
                                        units['time']))

        # Heat of Reaction
        if has_heat_of_reaction:
            @self.Expression(self.flowsheet().config.time,
                             self.length_domain,
                             doc="Heat of reaction term at point x [{}/{}.{}]"
                                 .format(units['energy'],
                                         units['length'],
                                         units['time']))
            def heat_of_reaction(b, t, x):
                if hasattr(self, "rate_reaction_extent"):
                    rate_heat = -sum(b.rate_reaction_extent[t, x, r] *
                                     b.reactions[t, x].dh_rxn[r]
                                     for r in self.config.reaction_package.
                                     rate_reaction_idx)
                else:
                    rate_heat = 0

                if hasattr(self, "equilibrium_reaction_extent"):
                    equil_heat = -sum(
                            b.equilibrium_reaction_extent[t, x, e] *
                            b.reactions[t, x].dh_rxn[e]
                            for e in self.config.reaction_package.
                            equilibrium_reaction_idx)
                else:
                    equil_heat = 0

                return rate_heat + equil_heat

        # Create rules to substitute energy balance terms
        # Accumulation term
        def accumulation_term(b, t, x, p):
            return b.energy_accumulation[t, x, p] if dynamic else 0

        def heat_term(b, t, x):
            return b.heat[t, x] if has_heat_transfer else 0

        def work_term(b, t, x):
            return b.work[t, x] if has_work_transfer else 0

        def rxn_heat_term(b, t, x):
            return b.heat_of_reaction[t, x] if has_heat_of_reaction else 0

        # Custom term
        def user_term(t, x):
            if custom_term is not None:
                return custom_term(t, x)
            else:
                return 0

        # Energy balance equation
        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         doc="Energy balances")
        def enthalpy_balances(b, t, x):
            if ((b.config.transformation_scheme != "FORWARD" and
                 x == b.length_domain.first()) or
                    (b.config.transformation_scheme == "FORWARD" and
                     x == b.length_domain.last())):
                return Constraint.Skip
            else:
                return (b.length*sum(
                        accumulation_term(b, t, x, p) for p in
                        b.config.property_package.phase_list) *
                        b.scaling_factor_energy) == (
                    b._flow_direction_term * sum(b.enthalpy_flow_dx[t, x, p]
                                                 for p in b.config.
                                                 property_package.phase_list) *
                    b.scaling_factor_energy +
                    b.length*heat_term(b, t, x)*b.scaling_factor_energy +
                    b.length*work_term(b, t, x)*b.scaling_factor_energy +
                    b.length*rxn_heat_term(b, t, x)*b.scaling_factor_energy +
                    b.length*user_term(t, x)*b.scaling_factor_energy)
                    # TODO : Add conduction/dispersion term

        # Energy Holdup
        if has_holdup:
            if not hasattr(self, "phase_fraction"):
                self._add_phase_fractions()

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             self.config.property_package.phase_list,
                             doc="Enthalpy holdup constraint")
            def enthalpy_holdup_calculation(b, t, x, p):
                return b.energy_holdup[t, x, p] == (
                    b._area_func(t, x) * self.phase_fraction[t, x, p] *
                    b.properties[t, x].get_energy_density_terms(p))

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
        This method constructs a set of 1D pressure balances indexed by time.

        Args:
            has_pressure_change - whether terms for pressure change should be
                    included in enthalpy balances
            custom_term - a Pyomo Expression representing custom terms to
                    be included in pressure balances.
                    Expression must be indexed by time and length domain

        Returns:
            Constraint object representing pressure balances
        """
        # Get units from property package
        units = {}
        for u in ['length', 'pressure']:
            try:
                units[u] = \
                   self.config.property_package.get_metadata().default_units[u]
            except KeyError:
                units[u] = '-'

        # Create dP/dx terms
        # TODO : Replace with Reference if possible
        self.pressure = Var(self.flowsheet().config.time,
                            self.length_domain,
                            initialize=1e5,
                            doc="Pressure {}".format(units["pressure"]))

        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         doc="Equating local pressure to StateBlocks")
        def pressure_linking_constraint(b, t, x):
            return b.pressure[t, x] == b.properties[t, x].pressure

        self.pressure_dx = DerivativeVar(
                                  self.pressure,
                                  wrt=self.length_domain,
                                  doc="Partial derivative of pressure wrt "
                                      "normalized length domain")

        # Add Momentum Balance Variables as necessary
        if has_pressure_change:
            self.deltaP = Var(self.flowsheet().config.time,
                              self.length_domain,
                              domain=Reals,
                              initialize=0.0,
                              doc="Pressure difference per unit length "
                                  "of domain [{}/{}]"
                                  .format(units["pressure"],
                                          units["length"]))

        # Create rules to substitute energy balance terms
        # Pressure change term
        def deltaP_term(b, t, x):
            return b.deltaP[t, x] if has_pressure_change else 0

        # Custom term
        def user_term(t, x):
            if custom_term is not None:
                return custom_term(t, x)
            else:
                return 0

        # Create scaling factor
        self.scaling_factor_pressure = Param(
                    default=1e-4,
                    mutable=True,
                    doc='Momentum balance scaling parameter')

        # Momentum balance equation
        @self.Constraint(self.flowsheet().config.time,
                         self.length_domain,
                         doc='Momentum balance')
        def pressure_balance(b, t, x):
            if ((b.config.transformation_scheme != "FORWARD" and
                 x == b.length_domain.first()) or
                    (b.config.transformation_scheme == "FORWARD" and
                     x == b.length_domain.last())):
                return Constraint.Skip
            else:
                return 0 == (b._flow_direction_term*b.pressure_dx[t, x] *
                             b.scaling_factor_pressure +
                             b.length*deltaP_term(b, t, x) *
                             b.scaling_factor_pressure +
                             b.length*user_term(t, x) *
                             b.scaling_factor_pressure)

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

    def apply_transformation(self):
        """
        Method to apply DAE transformation to the Control Volume length domain.
        Transformation applied will be based on the Control Volume
        configuration arguments.
        """
        if self.length_domain.parent_block() != self:
            raise ConfigurationError(
                    "{} tried to apply a DAE transformation to an external "
                    "domain. To avoid complications, the apply_transformation "
                    "method only supports transformation of local domains."
                    .format(self.name))

        if self.config.finite_elements is None:
            raise ConfigurationError(
                    "{} was not provided a value for the finite_elements"
                    " configuration argument. Please provide a valid value."
                    .format(self.name))

        if (self.config.collocation_points is None and
                self.config.transformation_method == "dae.collocation"):
            raise ConfigurationError(
                    "{} was not provided a value for the collocation_points"
                    " configuration argument. Please provide a valid value."
                    .format(self.name))

        if self.config.transformation_method == "dae.finite_difference":
            self.discretizer = TransformationFactory(
                                    self.config.transformation_method)
            self.discretizer.apply_to(self,
                                      nfe=self.config.finite_elements,
                                      wrt=self.length_domain,
                                      scheme=self.config.transformation_scheme)
        elif self.config.transformation_method == "dae.collocation":
            self.discretizer = TransformationFactory(
                                    self.config.transformation_method)
            self.discretizer.apply_to(
                self,
                wrt=self.length_domain,
                nfe=self.config.finite_elements,
                ncp=self.config.collocation_points,
                scheme=self.config.transformation_scheme)
        else:
            raise ConfigurationError("{} unrecognised transfromation_method, "
                                     "must match one of the Transformations "
                                     "supported by Pyomo's "
                                     "TransformationFactory."
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
            for x in blk.length_domain:
                try:
                    blk.properties[t, x].model_check()
                except AttributeError:
                    _log.warning(
                        '{} ControlVolume StateBlock has no '
                        'model checks. To correct this, add a model_check'
                        ' method to the associated StateBlock class.'
                        .format(blk.name))

                try:
                    blk.reactions[t, x].model_check()
                except AttributeError:
                    _log.warning(
                        '{} ControlVolume outlet reaction block has no '
                        'model check. To correct this, add a '
                        'model_check method to the associated '
                        'ReactionBlock class.'.format(blk.name))

    def initialize(blk, state_args=None, outlvl=idaeslog.NOTSET, optarg=None,
                   solver='ipopt', hold_state=True):
        '''
        Initialization routine for 1D control volume (default solver ipopt)

        Keyword Arguments:
            state_args : a dict of arguments to be passed to the property
                         package(s) to provide an initial state for
                         initialization (see documentation of the specific
                         property package) (default = {}).
            outlvl : sets output level of initialization routine
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
            states were fixed during initialization else the release state is
            triggered.
        '''
        # Get inlet state if not provided
        init_log = idaeslog.getInitLogger(blk.name, outlvl, tag="control_volume")

        # Get source block
        if blk._flow_direction == FlowDirection.forward:
            source_idx = blk.length_domain.first()
        else:
            source_idx = blk.length_domain.last()
        source = blk.properties[blk.flowsheet().config.time.first(),
                                source_idx]

        # Fix source state and get state_args if not provided
        source_flags = {}
        if state_args is None:
            # No state args, create whilst fixing vars
            state_args = {}
            # Should be checking flow direction
            state_dict = source.define_port_members()

            for k in state_dict.keys():
                if state_dict[k].is_indexed():
                    state_args[k] = {}
                    source_flags[k] = {}
                    for m in state_dict[k].keys():
                        source_flags[k][m] = state_dict[k][m].fixed
                        if state_dict[k][m].value is not None:
                            state_dict[k][m].fix()
                            state_args[k][m] = state_dict[k][m].value
                        else:
                            raise Exception("State variables have not been "
                                            "fixed nor have been given "
                                            "initial values.")
                else:
                    source_flags[k] = state_dict[k].fixed
                    if state_dict[k].value is not None:
                        state_dict[k].fix()
                        state_args[k] = state_dict[k].value
                    else:
                        raise Exception("State variables have not been "
                                        "fixed nor have been given "
                                        "initial values.")
        else:
            # State  args provided
            state_dict = source.define_port_members()

            for k in state_dict.keys():
                source_flags[k] = {}
                if state_dict[k].is_indexed():
                    for m in state_dict[k].keys():
                        source_flags[k][m] = state_dict[k][m].fixed
                        if not state_dict[k][m].fixed:
                            state_dict[k][m].fix(state_args[k][m])
                else:
                    source_flags[k] = state_dict[k].fixed
                    if state_dict[k].value is not None:
                        state_dict[k].fix()
                        if not state_dict[k].fixed:
                            state_dict[k].fix(state_args[k])

        # Initialize state blocks
        flags = blk.properties.initialize(
            state_args=state_args,
            outlvl=outlvl,
            optarg=optarg,
            solver=solver,
            hold_state=True,
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

        init_log.info('Initialization Complete')

        # Unfix state variables except for source block
        blk.properties.release_state(flags)

        if hold_state is True:
            return source_flags
        else:
            blk.release_state(source_flags)

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
        # Get source block
        if blk._flow_direction == FlowDirection.forward:
            source_idx = blk.length_domain.first()
        else:
            source_idx = blk.length_domain.last()
        source = blk.properties[blk.flowsheet().config.time.first(),
                                source_idx]

        # Set fixed attribute on state vars based on flags
        state_dict = source.define_port_members()

        for k in state_dict.keys():
            if state_dict[k].is_indexed():
                for m in state_dict[k].keys():
                    state_dict[k][m].fixed = flags[k][m]
            else:
                state_dict[k].fixed = flags[k]

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
                            self.length_domain,
                            self.config.property_package.phase_list,
                            initialize=1 / len(self.config.
                                               property_package.phase_list),
                            doc='Volume fraction of holdup by phase')

            @self.Constraint(self.flowsheet().config.time,
                             self.length_domain,
                             doc='Sum of phase fractions == 1')
            def sum_of_phase_fractions(b, t, x):
                return 1 == sum(
                        b.phase_fraction[t, x, p]
                        for p in self.config.property_package.phase_list)
        else:
            @self.Expression(self.flowsheet().config.time,
                             self.length_domain,
                             self.config.property_package.phase_list,
                             doc='Volume fraction of holdup by phase')
            def phase_fraction(self, t, x, p):
                return 1

    def _area_func(b, t, x):
        if b.config.area_definition == DistributedVars.uniform:
            return b.area
        return b.area[t, x]

    def report(self, time_point=0, dof=False, ostream=None, prefix=""):
        """
        No report method defined for ControlVolume1D class. This is due to the
        difficulty of presenting spatially discretized data in a readable form
        without plotting.
        """
        raise NotImplementedError("""
                Due ot the difficultly in presenting spatially distributed data
                in a clean format, ControlVolume1D does not currently support
                the report method.""")
