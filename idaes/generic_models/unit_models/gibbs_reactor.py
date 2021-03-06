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
Standard IDAES Gibbs reactor model.
"""
# Import Pyomo libraries
from pyomo.environ import Reals, Var
from pyomo.common.config import ConfigBlock, ConfigValue, In

# Import IDAES cores
from idaes.core import (ControlVolume0DBlock,
                        declare_process_block_class,
                        EnergyBalanceType,
                        MomentumBalanceType,
                        UnitModelBlockData,
                        useDefault)
from idaes.core.util.config import is_physical_parameter_block
from idaes.core.util.misc import add_object_reference

__author__ = "Jinliang Ma, Andrew Lee"


@declare_process_block_class("GibbsReactor")
class GibbsReactorData(UnitModelBlockData):
    """
    Standard Gibbs Reactor Unit Model Class

    This model assume all possible reactions reach equilibrium such that the
    system partial molar Gibbs free energy is minimized.
    Since some species mole flow rate might be very small,
    the natural log of the species molar flow rate is used.
    Instead of specifying the system Gibbs free energy as an objective
    function, the equations for zero partial derivatives of the grand function
    with Lagrangian multiple terms with repect to product species mole flow
    rates and the multiples are specified as constraints.
    """
    CONFIG = ConfigBlock()
    CONFIG.declare("dynamic", ConfigValue(
        domain=In([False]),
        default=False,
        description="Dynamic model flag - must be False",
        doc="""Gibbs reactors do not support dynamic models, thus this must be
False."""))
    CONFIG.declare("has_holdup", ConfigValue(
        default=False,
        domain=In([False]),
        description="Holdup construction flag",
        doc="""Gibbs reactors do not have defined volume, thus this must be
False."""))
    CONFIG.declare("energy_balance_type", ConfigValue(
        default=EnergyBalanceType.useDefault,
        domain=In(EnergyBalanceType),
        description="Energy balance construction flag",
        doc="""Indicates what type of energy balance should be constructed,
**default** - EnergyBalanceType.useDefault.
**Valid values:** {
**EnergyBalanceType.useDefault - refer to property package for default
balance type
**EnergyBalanceType.none** - exclude energy balances,
**EnergyBalanceType.enthalpyTotal** - single enthalpy balance for material,
**EnergyBalanceType.enthalpyPhase** - enthalpy balances for each phase,
**EnergyBalanceType.energyTotal** - single energy balance for material,
**EnergyBalanceType.energyPhase** - energy balances for each phase.}"""))
    CONFIG.declare("momentum_balance_type", ConfigValue(
        default=MomentumBalanceType.pressureTotal,
        domain=In(MomentumBalanceType),
        description="Momentum balance construction flag",
        doc="""Indicates what type of momentum balance should be constructed,
**default** - MomentumBalanceType.pressureTotal.
**Valid values:** {
**MomentumBalanceType.none** - exclude momentum balances,
**MomentumBalanceType.pressureTotal** - single pressure balance for material,
**MomentumBalanceType.pressurePhase** - pressure balances for each phase,
**MomentumBalanceType.momentumTotal** - single momentum balance for material,
**MomentumBalanceType.momentumPhase** - momentum balances for each phase.}"""))
    CONFIG.declare("has_heat_transfer", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Heat transfer term construction flag",
        doc="""Indicates whether terms for heat transfer should be constructed,
**default** - False.
**Valid values:** {
**True** - include heat transfer terms,
**False** - exclude heat transfer terms.}"""))
    CONFIG.declare("has_pressure_change", ConfigValue(
        default=False,
        domain=In([True, False]),
        description="Pressure change term construction flag",
        doc="""Indicates whether terms for pressure change should be
constructed,
**default** - False.
**Valid values:** {
**True** - include pressure change terms,
**False** - exclude pressure change terms.}"""))
    CONFIG.declare("property_package", ConfigValue(
        default=useDefault,
        domain=is_physical_parameter_block,
        description="Property package to use for control volume",
        doc="""Property parameter object used to define property calculations,
**default** - useDefault.
**Valid values:** {
**useDefault** - use default package from parent model or flowsheet,
**PropertyParameterObject** - a PropertyParameterBlock object.}"""))
    CONFIG.declare("property_package_args", ConfigBlock(
        implicit=True,
        description="Arguments to use for constructing property packages",
        doc="""A ConfigBlock with arguments to be passed to a property block(s)
and used when constructing these,
**default** - None.
**Valid values:** {
see property package for documentation.}"""))

    def build(self):
        """
        Begin building model (pre-DAE transformation).

        Args:
            None

        Returns:
            None
        """
        # Call UnitModel.build to setup dynamics
        super(GibbsReactorData, self).build()

        # Build Control Volume
        self.control_volume = ControlVolume0DBlock(default={
                "dynamic": self.config.dynamic,
                "property_package": self.config.property_package,
                "property_package_args": self.config.property_package_args})

        self.control_volume.add_state_blocks(has_phase_equilibrium=False)

        self.control_volume.add_total_element_balances()

        self.control_volume.add_energy_balances(
            balance_type=self.config.energy_balance_type,
            has_heat_transfer=self.config.has_heat_transfer)

        self.control_volume.add_momentum_balances(
            balance_type=self.config.momentum_balance_type,
            has_pressure_change=self.config.has_pressure_change)

        # Add Ports
        self.add_inlet_port()
        self.add_outlet_port()

        # Add performance equations
        # Add Lagrangian multiplier variables
        self.lagrange_mult = Var(self.flowsheet().config.time,
                                 self.config.property_package.element_list,
                                 domain=Reals,
                                 initialize=100,
                                 doc="Lagrangian multipliers")

        # Use Lagrangian multiple method to derive equations for Out_Fi
        # Use RT*lagrange as the Lagrangian multiple such that lagrange is in
        # a similar order of magnitude as log(Yi)

        @self.Constraint(self.flowsheet().config.time,
                         self.config.property_package.phase_list,
                         self.config.property_package.component_list,
                         doc="Gibbs energy minimisation constraint")
        def gibbs_minimization(b, t, p, j):
            # Use natural log of species mole flow to avoid Pyomo solver
            # warnings of reaching infeasible point
            return 0 == (
                b.control_volume.properties_out[t].gibbs_mol_phase_comp[p, j] +
                sum(b.lagrange_mult[t, e] *
                    b.control_volume.properties_out[t].
                    config.parameters.element_comp[j][e]
                    for e in b.config.property_package.element_list))

        # Set references to balance terms at unit level
        if (self.config.has_heat_transfer is True and
                self.config.energy_balance_type != EnergyBalanceType.none):
            add_object_reference(self,
                                 "heat_duty",
                                 self.control_volume.heat)
        if (self.config.has_pressure_change is True and
                self.config.momentum_balance_type != MomentumBalanceType.none):
            add_object_reference(self,
                                 "deltaP",
                                 self.control_volume.deltaP)

    def _get_performance_contents(self, time_point=0):
        var_dict = {}
        if hasattr(self, "heat_duty"):
            var_dict["Heat Duty"] = self.heat_duty[time_point]
        if hasattr(self, "deltaP"):
            var_dict["Pressure Change"] = self.deltaP[time_point]

        return {"vars": var_dict}
