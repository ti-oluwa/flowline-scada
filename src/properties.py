import enum
import typing
import attrs
import math
from pint.facets.plain import PlainQuantity
from CoolProp.CoolProp import PropsSI

from src.units import ureg, Quantity


WATER_DENSITY = Quantity(
    999.1, "kg/m^3"
)  # Density of water at standard conditions - 1atm and 15°C
AIR_DENSITY = Quantity(
    1.225, "kg/m^3"
)  # Density of air at standard conditions - 1atm and 15°C


@attrs.define
class Fluid:
    """Model representing a fluid with its properties."""

    name: str = attrs.field()
    """Name of the fluid"""
    phase: typing.Literal["liquid", "gas"] = attrs.field()
    """Phase of the fluid: 'liquid' or 'gas'"""
    density: PlainQuantity[float] = attrs.field()
    """Density of the fluid"""
    viscosity: PlainQuantity[float] = attrs.field()
    """Dynamic viscosity of the fluid"""
    temperature: PlainQuantity[float] = attrs.field()
    """Temperature of the fluid"""
    molecular_weight: PlainQuantity[float] = attrs.field()
    """Molecular weight of the fluid"""
    compressibility_factor: float = attrs.field(default=0.0)
    """Compressibility factor of the fluid (if applicable) e.g., for gases"""

    def __attrs_post_init__(self):
        if self.phase == "gas" and self.compressibility_factor <= 0.0:
            raise ValueError("Compressibility factor must be provided for gas phase.")

    @property
    def specific_gravity(self) -> float:
        """
        The specific gravity of the fluid.
        """
        if self.phase == "gas":
            return (
                self.density.to("kg/m^3").magnitude / AIR_DENSITY.to("kg/m^3").magnitude
            )
        return (
            self.density.to("kg/m^3").magnitude / WATER_DENSITY.to("kg/m^3").magnitude
        )

    @classmethod
    def from_coolprop(
        cls,
        fluid_name: str,
        pressure: PlainQuantity[float],
        temperature: PlainQuantity[float],
        phase: typing.Literal["liquid", "gas"],
        molecular_weight: typing.Optional[PlainQuantity[float]] = None,
    ) -> "Fluid":
        """
        Create a Fluid instance by querying CoolProp for properties.

        :param fluid_name: Name of the fluid as recognized by CoolProp
                           (e.g., "Methane", "CO2", "Water", "Nitrogen").
        :param pressure: Fluid pressure (as a Quantity, convertible to Pa).
        :param temperature: Fluid temperature (as a Quantity, convertible to K).
        :param phase: Phase of the fluid: 'liquid' or 'gas'.
        :return: Fluid instance with properties populated from CoolProp.
        """
        density = compute_fluid_density(pressure, temperature, fluid_name)
        viscosity = compute_fluid_viscosity(pressure, temperature, fluid_name)
        if molecular_weight is None:
            molecular_weight = compute_molecular_weight(fluid_name)

        compressibility_factor = 0.0
        if phase == "gas":
            compressibility_factor = compute_fluid_compressibility_factor(
                pressure, temperature, fluid_name
            ).magnitude

        return cls(
            name=fluid_name,
            phase=phase,
            density=density,
            viscosity=viscosity,
            temperature=temperature,
            molecular_weight=molecular_weight,
            compressibility_factor=compressibility_factor,
        )


def compute_fluid_density(
    pressure: PlainQuantity[float],
    temperature: PlainQuantity[float],
    fluid_name: str,
) -> PlainQuantity[float]:
    """
    Compute the fluid density using CoolProp.

    :param pressure: Fluid pressure (as a Quantity, convertible to Pa).
    :param temperature: Fluid temperature (as a Quantity, convertible to K).
    :param fluid_name: Name of the fluid as recognized by CoolProp
                       (e.g., "Methane", "CO2", "Water", "Nitrogen").
    :return: Fluid density as a Quantity (kg/m^3).
    """
    pressure_pa = pressure.to("Pa").magnitude
    temperature_k = temperature.to("K").magnitude

    # Query CoolProp
    density_kg_per_m3 = PropsSI(
        "Dmass", "P", pressure_pa, "T", temperature_k, fluid_name
    )
    return Quantity(density_kg_per_m3, "kg/m^3")


def compute_molecular_weight(fluid_name: str) -> PlainQuantity[float]:
    """
    Compute the molecular weight of a fluid using CoolProp.

    :param fluid_name: Name of the fluid as recognized by CoolProp
                       (e.g., "Methane", "CO2", "Water", "Nitrogen").
    :return: Molecular weight of the fluid as a Quantity (kg/mol).
    """
    molecular_weight_kg_per_mol = PropsSI("M", "P", 101325, "T", 298.15, fluid_name)
    return Quantity(molecular_weight_kg_per_mol, "kg/mol")


def compute_fluid_viscosity(
    pressure: PlainQuantity[float],
    temperature: PlainQuantity[float],
    fluid_name: str,
) -> PlainQuantity[float]:
    """
    Compute the dynamic viscosity of a fluid using CoolProp.

    :param pressure: Fluid pressure (as a Quantity, convertible to Pa).
    :param temperature: Fluid temperature (as a Quantity, convertible to K).
    :param fluid_name: Name of the fluid as recognized by CoolProp
                       (e.g., "Methane", "CO2", "Water", "Nitrogen").
    :return: Dynamic viscosity of the fluid as a Quantity (Pa·s).
    """
    pressure_pa = pressure.to("Pa").magnitude
    temperature_k = temperature.to("K").magnitude

    viscosity_pa_s = PropsSI("V", "P", pressure_pa, "T", temperature_k, fluid_name)
    return Quantity(viscosity_pa_s, "Pa.s")


def compute_fluid_compressibility_factor(
    pressure: PlainQuantity[float],
    temperature: PlainQuantity[float],
    fluid_name: str,
) -> PlainQuantity[float]:
    """
    Compute the compressibility factor of a fluid using CoolProp.

    :param pressure: Fluid pressure (as a Quantity, convertible to Pa).
    :param temperature: Fluid temperature (as a Quantity, convertible to K).
    :param fluid_name: Name of the fluid as recognized by CoolProp
                       (e.g., "Methane", "CO2", "Water", "Nitrogen").
    :return: Compressibility factor of the fluid (dimensionless).
    """
    pressure_pa = pressure.to("Pa").magnitude
    temperature_k = temperature.to("K").magnitude

    compressibility_factor = PropsSI(
        "Z", "P", pressure_pa, "T", temperature_k, fluid_name
    )
    return Quantity(compressibility_factor, "dimensionless")


def compute_reynolds_number(
    current_flow_rate: PlainQuantity[float],
    pipe_internal_diameter: PlainQuantity[float],
    fluid_density: PlainQuantity[float],
    fluid_dynamic_viscosity: PlainQuantity[float],
) -> float:
    """
    Calculate the Reynolds number for flow in a circular pipe.

    :param current_flow_rate: Volumetric flow rate of the fluid (e.g., m^3/s).
    :param pipe_internal_diameter: Internal diameter of the pipe (e.g., m).
    :param fluid_density: Density of the fluid (e.g., kg/m^3).
    :param fluid_dynamic_viscosity: Dynamic viscosity of the fluid (e.g., Pa·s).
    :return: Dimensionless Reynolds number.
    """
    current_flow_rate_m3_per_s = current_flow_rate.to("m^3/s").magnitude
    pipe_internal_diameter_m = pipe_internal_diameter.to("m").magnitude
    fluid_density_kg_per_m3 = fluid_density.to("kg/m^3").magnitude
    fluid_dynamic_viscosity_pa_s = fluid_dynamic_viscosity.to("Pa.s").magnitude

    cross_sectional_area_m2 = math.pi * (pipe_internal_diameter_m**2) / 4.0
    average_velocity_m_per_s = current_flow_rate_m3_per_s / cross_sectional_area_m2

    reynolds_number = (
        fluid_density_kg_per_m3 * average_velocity_m_per_s * pipe_internal_diameter_m
    ) / fluid_dynamic_viscosity_pa_s
    return reynolds_number


def compute_darcy_weisbach_friction_factor(
    reynolds_number: float, relative_roughness: float = 0.0
) -> float:
    """
    Calculate the Darcy-Weisbach friction factor for flow in a pipe.

    The calculation uses different correlations depending on the flow regime:
    - Laminar flow (Re < 2000): f = 64 / Re
    - Transitional and turbulent flow:
        * For hydraulically smooth pipes with 4000 < Re < 100000,
          Blasius correlation is used.
        * Otherwise, the Colebrook-White equation is solved iteratively.

    param reynolds_number: Reynolds number of the flow (dimensionless).
    param relative_roughness: Pipe relative roughness (epsilon / D), default is 0 for smooth pipes.
    return: Darcy-Weisbach friction factor (dimensionless).
    """
    if reynolds_number < 2000:
        # Laminar flow
        return 64.0 / reynolds_number

    elif 2000 <= reynolds_number <= 100000 and relative_roughness == 0.0:
        # Blasius correlation for smooth turbulent pipe
        return 0.3164 * reynolds_number**-0.25

    # Colebrook-White equation solved iteratively (Newton-Raphson)
    friction_factor_guess = 0.02
    for _ in range(50):  # iterate for convergence
        rhs = -2.0 * math.log10(
            (relative_roughness / 3.7)
            + (2.51 / (reynolds_number * math.sqrt(friction_factor_guess)))
        )
        friction_factor_new = 1.0 / (rhs**2)
        if abs(friction_factor_new - friction_factor_guess) < 1e-6:
            break
        friction_factor_guess = friction_factor_new
    return friction_factor_guess


def compute_darcy_weisbach_flow_rate(
    length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    downstream_pressure: PlainQuantity[float],
    specific_gravity: float,
    friction_factor: float,
) -> PlainQuantity[float]:
    """
    Calculate the flow rate in a pipe using the Darcy-Weisbach equation
    in petroleum engineering (oilfield unit) form.

    This implementation uses an industry correlation form that consolidates
    constants and unit conversions into a single factor (0.0000115).
    The correlation assumes:
        - Pressure in psi
        - Length in feet
        - Internal diameter in inches
        - Specific gravity relative to water (ρ = SG * 62.4 lb/ft³)
        - Flow rate in barrels per day (bbl/day)

    The formula used is:

        Q = sqrt((ΔP * D^5) / (0.0000115 * f * L * SG))

    where:
    - Q is the flow rate in bbl/day
    - ΔP is the pressure drop in psi
    - D is the internal diameter in inches
    - f is the Darcy-Weisbach friction factor (dimensionless)
    - L is the length in feet
    - SG is the specific gravity of the fluid relative to water (dimensionless)

    param length: Pipe length as a Quantity (convertible to feet).
    param internal_diameter: Pipe internal diameter as a Quantity (convertible to inches).
    param upstream_pressure: Upstream absolute pressure as a Quantity (convertible to psi).
    param downstream_pressure: Downstream absolute pressure as a Quantity (convertible to psi).
    param specific_gravity: Fluid specific gravity relative to water (dimensionless).
    param friction_factor: Darcy-Weisbach friction factor (dimensionless).
    return: Flow rate as a Quantity (ft³/s).
    """
    pressure_drop = (
        upstream_pressure.to("psi").magnitude - downstream_pressure.to("psi").magnitude
    )
    internal_diameter_inches = internal_diameter.to("inches").magnitude
    length_feet = length.to("feet").magnitude

    flow_rate_in_bbl_per_day = math.sqrt(
        (pressure_drop * internal_diameter_inches**5)
        / (0.0000115 * friction_factor * length_feet * specific_gravity)
    ) * (ureg.bbl / ureg.day)
    return flow_rate_in_bbl_per_day.to("ft^3/s")  # type: ignore


def _compute_slope(
    gas_specific_gravity: float,
    elevation_difference: PlainQuantity[float],
    average_temperature: PlainQuantity[float] = Quantity(520, "degR"),
) -> float:
    """
    Compute the slope (s) for the compressible model equations.

    The slope is calculated as:

        s = (0.0375 * SG * Δh) / Tm

    where:
        - SG is the specific gravity of the gas relative to air (dimensionless)
        - Δh is the elevation difference in feet
        - Tm is the average temperature in Rankine (default 520°R for 60°F)

    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param elevation_difference: Elevation difference in feet.
    :param average_temperature: Average temperature in degrees Rankine (default 520°R).
    :return: Slope value (dimensionless).
    """
    elevation_difference_ft = elevation_difference.to("ft").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    return (
        0.0375 * gas_specific_gravity * elevation_difference_ft
    ) / average_temperature_rankine


def _correct_pipeline_length(
    pipeline_length: float,
    slope: float,
) -> float:
    """
    Correct the pipeline length based on the slope (s).

    If the slope is zero, the length remains unchanged. Otherwise, it is adjusted
    using the formula:

        L = (exp(s) - 1) * L / s

    where:
        - L is the original pipeline length
        - s is the slope calculated from `_compute_slope`

    :param pipeline_length: Original pipeline length.
    :param slope: Slope value (dimensionless).
    :return: Corrected pipeline length.
    """
    if slope == 0:
        return pipeline_length
    return (math.exp(slope) - 1) * pipeline_length / slope


def compute_weymouth_flow_rate(
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    downstream_pressure: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Compute the gas flow rate in a pipeline using the Weymouth equation.

    The Weymouth equation is used to estimate the volumetric gas flow rate
    through a pipeline under steady-state conditions.

    The formula used is:

        Q = 433.5 * (Tsc / Psc ) * ((P1^2 - [exp(s) * P2^2]) / (SG * L * T * Z))^0.5 * (D^2.667) * E

        s = (0.0375 * SG * Δh) / Tsc

        If s != 0:
            L = (exp(s) - 1) * L / s

    where:
        - Q is the flow rate in scf/day
        - Tsc is the standard temperature in Rankine (60°F = 520°R)
        - Psc is the standard pressure in psi (14.7 psi)
        - P1 is the upstream pressure in psi
        - P2 is the downstream pressure in psi
        - SG is the specific gravity of the gas relative to air (dimensionless)
        - L is the pipeline length in miles
        - T is the average gas temperature in degrees Rankine
        - Z is the compressibility factor (dimensionless)
        - D is the internal diameter of the pipe in inches
        - E is the pipeline efficiency factor (dimensionless)
        - Δh is the elevation difference in feet between upstream and downstream

    :param pipeline_length: Length of the pipeline (must be in miles).
    :param internal_diameter: Internal diameter of the pipe (must be in inches).
    :param upstream_pressure: Upstream pressure at the start of the pipeline (must be in psi).
    :param downstream_pressure: Downstream pressure at the end of the pipeline (must be in psi).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (must be in degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :return: Gas flow rate as a Pint Quantity in cubic feet per second (ft³/s).
    """
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    downstream_pressure_psi = downstream_pressure.to("psi").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7  # Standard pressure in psi
    standard_temperature_rankine = 520.0  # Standard temperature in Rankine (60°F)

    # Weymouth constant (from formula reference, 433.5 for miles)
    weymouth_constant = 433.5

    slope = _compute_slope(
        gas_specific_gravity,
        elevation_difference,
        average_temperature=average_temperature,
    )
    if slope == 0:
        # If slope is zero, we can avoid division by zero
        corrected_pipeline_length_miles = pipeline_length_miles

        # Pressure-squared difference term
        pressure_square_difference = (
            upstream_pressure_psi**2 - downstream_pressure_psi**2
        )
    else:
        corrected_pipeline_length_miles = _correct_pipeline_length(
            pipeline_length_miles, slope=slope
        )

        # Pressure-squared difference term
        pressure_square_difference = upstream_pressure_psi**2 - (
            math.exp(slope) * downstream_pressure_psi**2
        )

    # Denominator term: (gas_specific_gravity * pipeline_length * temperature * compressibility_factor)
    denominator = (
        gas_specific_gravity
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    flow_rate_scf_per_day = (
        weymouth_constant
        * (standard_temperature_rankine / standard_pressure_psi)
        * (pressure_square_difference / denominator) ** 0.5
        * (internal_diameter_inches**2.667)
        * pipeline_efficiency
    ) * (ureg.scf / ureg.day)
    return flow_rate_scf_per_day.to("ft^3/s")  # type: ignore


def compute_modified_panhandle_A_flow_rate(
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    downstream_pressure: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Compute the gas flow rate in a pipeline using the Modified Panhandle A equation.

    The Modified Panhandle A equation is used to estimate the volumetric gas flow rate
    through a pipeline under steady-state conditions.

    The formula used is:

        Q = 435.87 * (Tsc / Psc)^1.0788 * ((P1^2 - [exp(s) * P2^2]) / (SG^0.8539 * L * T * Z))^0.5394 * (D^2.6182) * E

        s = (0.0375 * SG * Δh) / Tsc

        If s != 0:
            L = (exp(s) - 1) * L / s

    where:
        - Q is the flow rate in scf/day
        - Tsc is the standard temperature in Rankine (60°F = 520°R)
        - Psc is the standard pressure in psi (14.7 psi)
        - P1 is the upstream pressure in psi
        - P2 is the downstream pressure in psi
        - SG is the specific gravity of the gas relative to air (dimensionless)
        - L is the pipeline length in miles
        - T is the average gas temperature in degrees Rankine
        - Z is the compressibility factor (dimensionless)
        - D is the internal diameter of the pipe in inches
        - E is the pipeline efficiency factor (dimensionless)
        - Δh is the elevation difference in feet between upstream and downstream

    :param pipeline_length: Length of the pipeline (must be in miles).
    :param internal_diameter: Internal diameter of the pipe (must be in inches).
    :param upstream_pressure: Upstream pressure at the start of the pipeline (must be in psi).
    :param downstream_pressure: Downstream pressure at the end of the pipeline (must be in psi).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (must be in degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :return: Gas flow rate as a Pint Quantity in cubic feet per second (ft³/s).
    """
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    downstream_pressure_psi = downstream_pressure.to("psi").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7  # Standard pressure in psi
    standard_temperature_rankine = 520.0  # Standard temperature in Rankine (60°F)

    # Panhandle B constant (from formula reference, 435.87 for miles)
    panhandle_B_constant = 435.87

    slope = _compute_slope(
        gas_specific_gravity,
        elevation_difference,
        average_temperature=average_temperature,
    )
    if slope == 0:
        # If slope is zero, we can avoid division by zero
        corrected_pipeline_length_miles = pipeline_length_miles

        # Pressure-squared difference term
        pressure_square_difference = (
            upstream_pressure_psi**2 - downstream_pressure_psi**2
        )
    else:
        corrected_pipeline_length_miles = _correct_pipeline_length(
            pipeline_length_miles, slope=slope
        )

        # Pressure-squared difference term
        pressure_square_difference = upstream_pressure_psi**2 - (
            math.exp(slope) * downstream_pressure_psi**2
        )

    # Denominator term: (gas_specific_gravity**0.8539 * pipeline_length * temperature * compressibility_factor)
    denominator: float = (
        gas_specific_gravity**0.8539
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    flow_rate_scf_per_day = (
        panhandle_B_constant
        * (standard_temperature_rankine / standard_pressure_psi) ** 1.0788
        * (pressure_square_difference / denominator) ** 0.5394
        * (internal_diameter_inches**2.6182)
        * pipeline_efficiency
    ) * (ureg.scf / ureg.day)
    return flow_rate_scf_per_day.to("ft^3/s")  # type: ignore


def compute_modified_panhandle_B_flow_rate(
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    downstream_pressure: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Compute the gas flow rate in a pipeline using the Modified Panhandle B equation.

    The Modified Panhandle B equation is used to estimate the volumetric gas flow rate
    through a pipeline under steady-state conditions.

    The formula used is:

        Q = 737 * (Tsc / Psc)^1.02 * ((P1^2 - [exp(s) * P2^2]) / (SG^0.961 * L * T * Z))^0.51 * (D^2.52) * E

        s = (0.0375 * SG * Δh) / Tsc

        If s != 0:
            L = (exp(s) - 1) * L / s

    where:
        - Q is the flow rate in scf/day
        - Tsc is the standard temperature in Rankine (60°F = 520°R)
        - Psc is the standard pressure in psi (14.7 psi)
        - P1 is the upstream pressure in psi
        - P2 is the downstream pressure in psi
        - SG is the specific gravity of the gas relative to air (dimensionless)
        - L is the pipeline length in miles
        - T is the average gas temperature in degrees Rankine
        - Z is the compressibility factor (dimensionless)
        - D is the internal diameter of the pipe in inches
        - E is the pipeline efficiency factor (dimensionless)
        - Δh is the elevation difference in feet between upstream and downstream

    :param pipeline_length: Length of the pipeline (must be in miles).
    :param internal_diameter: Internal diameter of the pipe (must be in inches).
    :param upstream_pressure: Upstream pressure at the start of the pipeline (must be in psi).
    :param downstream_pressure: Downstream pressure at the end of the pipeline (must be in psi).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (must be in degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :return: Gas flow rate as a Pint Quantity in cubic feet per second (ft³/s).
    """
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    downstream_pressure_psi = downstream_pressure.to("psi").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7  # Standard pressure in psi
    standard_temperature_rankine = 520.0  # Standard temperature in Rankine (60°F)

    # Panhandle B constant (from formula reference, 737 for miles)
    panhandle_B_constant = 737

    slope = _compute_slope(
        gas_specific_gravity,
        elevation_difference,
        average_temperature=average_temperature,
    )
    if slope == 0:
        # If slope is zero, we can avoid division by zero
        corrected_pipeline_length_miles = pipeline_length_miles

        # Pressure-squared difference term
        pressure_square_difference = (
            upstream_pressure_psi**2 - downstream_pressure_psi**2
        )
    else:
        corrected_pipeline_length_miles = _correct_pipeline_length(
            pipeline_length_miles, slope=slope
        )

        # Pressure-squared difference term
        pressure_square_difference = upstream_pressure_psi**2 - (
            math.exp(slope) * downstream_pressure_psi**2
        )

    # Denominator term: (gas_specific_gravity**0.961 * pipeline_length * temperature * compressibility_factor)
    denominator: float = (
        gas_specific_gravity**0.961
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    flow_rate_scf_per_day = (
        panhandle_B_constant
        * (standard_temperature_rankine / standard_pressure_psi) ** 1.02
        * (pressure_square_difference / denominator) ** 0.51
        * (internal_diameter_inches**2.52)
        * pipeline_efficiency
    ) * (ureg.scf / ureg.day)
    return flow_rate_scf_per_day.to("ft^3/s")  # type: ignore


def compute_darcy_weisbach_pressure_drop(
    flow_rate: PlainQuantity[float],
    length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    specific_gravity: float,
    friction_factor: float,
) -> PlainQuantity[float]:
    """
    Calculate the pressure drop in a pipe using the Darcy-Weisbach equation
    given a flow rate.

    This function calculates pressure drop from flow rate using the rearranged
    Darcy-Weisbach equation in petroleum engineering form:

        ΔP = (0.0000115 * f * L * SG * Q^2) / D^5

    where:
    - ΔP is the pressure drop in psi
    - f is the Darcy-Weisbach friction factor (dimensionless)
    - L is the length in feet
    - SG is the specific gravity relative to water (dimensionless)
    - Q is the flow rate in bbl/day
    - D is the internal diameter in inches

    :param flow_rate: Flow rate as a Quantity (convertible to bbl/day).
    :param length: Pipe length as a Quantity (convertible to feet).
    :param internal_diameter: Pipe internal diameter as a Quantity (convertible to inches).
    :param specific_gravity: Fluid specific gravity relative to water (dimensionless).
    :param friction_factor: Darcy-Weisbach friction factor (dimensionless).
    :return: Pressure drop as a Quantity (psi).
    """
    flow_rate_bbl_per_day = flow_rate.to("bbl/day").magnitude
    length_feet = length.to("ft").magnitude
    internal_diameter_inches = internal_diameter.to("inches").magnitude

    pressure_drop_psi = (
        0.0000115
        * friction_factor
        * length_feet
        * specific_gravity
        * flow_rate_bbl_per_day**2
    ) / (internal_diameter_inches**5)
    return pressure_drop_psi * ureg.psi


def compute_weymouth_pressure_drop(
    upstream_pressure: PlainQuantity[float],
    flow_rate: PlainQuantity[float],
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Calculate the pressure drop in a pipeline using the Weymouth equation
    given a flow rate.

    This function rearranges the Weymouth equation to solve for pressure drop:

        ∆P^2 = P1^2 - [exp(s) * P2^2] = (Q / (433.5 * (Tsc/Psc) * D^2.667 * E))^2 * (SG * L * T * Z)
        ∆P = P1 - P2
        P2^2 =( P1^2 - ∆P^2) / exp(s)
        P2 = sqrt(P2^2)
        ∆P = P1 - P2

    where s is the slope factor and L is corrected for elevation.

    :param upstream_pressure: Upstream pressure at the start of the pipeline (convertible to psi).
    :param flow_rate: Gas flow rate as a Quantity (convertible to scf/day).
    :param pipeline_length: Length of the pipeline (convertible to miles).
    :param internal_diameter: Internal diameter of the pipe (convertible to inches).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (convertible to degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :param elevation_difference: Elevation difference between upstream and downstream (default 0 ft).
    :return: Pressure drop as a Quantity (psi).
    """
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    flow_rate_scf_per_day = flow_rate.to("scf/day").magnitude
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7
    standard_temperature_rankine = 520.0
    weymouth_constant = 433.5

    # Calculate slope and corrected length
    slope = _compute_slope(
        gas_specific_gravity, elevation_difference, average_temperature
    )
    corrected_pipeline_length_miles = _correct_pipeline_length(
        pipeline_length_miles, slope
    )

    # Rearrange Weymouth equation to solve for pressure squared difference
    denominator_flow = (
        weymouth_constant
        * (standard_temperature_rankine / standard_pressure_psi)
        * (internal_diameter_inches**2.667)
        * pipeline_efficiency
    )

    numerator_pressure = (
        gas_specific_gravity
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    pressure_squared_difference = (
        flow_rate_scf_per_day / denominator_flow
    ) ** 2 * numerator_pressure
    downstream_pressure_squared = (
        upstream_pressure_psi**2 - pressure_squared_difference
    ) / math.exp(slope)
    downstream_pressure_squared = max(
        downstream_pressure_squared, 0
    )  # Prevent negative due to rounding
    downstream_pressure = math.sqrt(downstream_pressure_squared)
    pressure_drop = upstream_pressure_psi - downstream_pressure
    return pressure_drop * ureg.psi


def compute_modified_panhandle_A_pressure_drop(
    upstream_pressure: PlainQuantity[float],
    flow_rate: PlainQuantity[float],
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Calculate the pressure drop in a pipeline using the Modified Panhandle A equation
    given a flow rate.

    This function rearranges the Modified Panhandle A equation to solve for pressure drop:

        P1^2 - [exp(s) * P2^2] = (Q / (435.87 * (Tsc/Psc)^1.0788 * D^2.6182 * E))^(2/1.0788) * (SG^0.8539 * L * T * Z)
        ∆P = P1 - P2
        P2^2 =( P1^2 - ∆P^2) / exp(s)
        P2 = sqrt(P2^2)
        ∆P = P1 - P2

    :param upstream_pressure: Upstream pressure at the start of the pipeline (convertible to psi).
    :param flow_rate: Gas flow rate as a Quantity (convertible to scf/day).
    :param pipeline_length: Length of the pipeline (convertible to miles).
    :param internal_diameter: Internal diameter of the pipe (convertible to inches).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (convertible to degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :param elevation_difference: Elevation difference between upstream and downstream (default 0 ft).
    :return: Pressure drop as a Quantity (psi).
    """
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    flow_rate_scf_per_day = flow_rate.to("scf/day").magnitude
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7
    standard_temperature_rankine = 520.0
    panhandle_A_constant = 435.87

    # Calculate slope and corrected length
    slope = _compute_slope(
        gas_specific_gravity, elevation_difference, average_temperature
    )
    corrected_pipeline_length_miles = _correct_pipeline_length(
        pipeline_length_miles, slope
    )

    # Rearrange Modified Panhandle A equation to solve for pressure squared difference
    denominator_flow: float = (
        panhandle_A_constant
        * (standard_temperature_rankine / standard_pressure_psi) ** 1.0788
        * (internal_diameter_inches**2.6182)
        * pipeline_efficiency
    )

    numerator_pressure: float = (
        gas_specific_gravity**0.8539
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    pressure_squared_difference = (flow_rate_scf_per_day / denominator_flow) ** (
        2 / 0.5394
    ) * numerator_pressure
    downstream_pressure_squared = (
        upstream_pressure_psi**2 - pressure_squared_difference
    ) / math.exp(slope)
    downstream_pressure_squared = max(
        downstream_pressure_squared, 0
    )  # Prevent negative due to rounding
    downstream_pressure = math.sqrt(downstream_pressure_squared)
    pressure_drop = upstream_pressure_psi - downstream_pressure
    return pressure_drop * ureg.psi


def compute_modified_panhandle_B_pressure_drop(
    upstream_pressure: PlainQuantity[float],
    flow_rate: PlainQuantity[float],
    pipeline_length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    gas_specific_gravity: float,
    average_temperature: PlainQuantity[float],
    compressibility_factor: float,
    pipeline_efficiency: float,
    elevation_difference: PlainQuantity[float] = Quantity(0, "ft"),
) -> PlainQuantity[float]:
    """
    Calculate the pressure drop in a pipeline using the Modified Panhandle B equation
    given a flow rate.

    This function rearranges the Modified Panhandle B equation to solve for pressure drop:

        P1^2 - [exp(s) * P2^2] = (Q / (737 * (Tsc/Psc)^1.02 * D^2.52 * E))^(2/1.02) * (SG^0.961 * L * T * Z)
        ∆P = P1 - P2
        P2^2 =( P1^2 - ∆P^2) / exp(s)
        P2 = sqrt(P2^2)
        ∆P = P1 - P2

    :param upstream_pressure: Upstream pressure at the start of the pipeline (convertible to psi).
    :param flow_rate: Gas flow rate as a Quantity (convertible to scf/day).
    :param pipeline_length: Length of the pipeline (convertible to miles).
    :param internal_diameter: Internal diameter of the pipe (convertible to inches).
    :param gas_specific_gravity: Specific gravity of the gas relative to air (dimensionless).
    :param average_temperature: Average gas temperature (convertible to degrees Rankine).
    :param compressibility_factor: Average compressibility factor Z (dimensionless).
    :param pipeline_efficiency: Pipeline efficiency factor E (dimensionless).
    :param elevation_difference: Elevation difference between upstream and downstream (default 0 ft).
    :return: Pressure drop as a Quantity (psi).
    """
    upstream_pressure_psi = upstream_pressure.to("psi").magnitude
    flow_rate_scf_per_day = flow_rate.to("scf/day").magnitude
    pipeline_length_miles = pipeline_length.to("mile").magnitude
    internal_diameter_inches = internal_diameter.to("inch").magnitude
    average_temperature_rankine = average_temperature.to("degR").magnitude
    standard_pressure_psi = 14.7
    standard_temperature_rankine = 520.0
    panhandle_B_constant = 737

    # Calculate slope and corrected length
    slope = _compute_slope(
        gas_specific_gravity, elevation_difference, average_temperature
    )
    corrected_pipeline_length_miles = _correct_pipeline_length(
        pipeline_length_miles, slope
    )

    # Rearrange Modified Panhandle B equation to solve for pressure squared difference
    denominator_flow: float = (
        panhandle_B_constant
        * (standard_temperature_rankine / standard_pressure_psi) ** 1.02
        * (internal_diameter_inches**2.52)
        * pipeline_efficiency
    )

    numerator_pressure: float = (
        gas_specific_gravity**0.961
        * corrected_pipeline_length_miles
        * average_temperature_rankine
        * compressibility_factor
    )

    pressure_squared_difference = (flow_rate_scf_per_day / denominator_flow) ** (
        2 / 0.51
    ) * numerator_pressure
    downstream_pressure_squared = (
        upstream_pressure_psi**2 - pressure_squared_difference
    ) / math.exp(slope)
    downstream_pressure_squared = max(
        downstream_pressure_squared, 0
    )  # Prevent negative due to rounding
    downstream_pressure = math.sqrt(downstream_pressure_squared)
    pressure_drop = upstream_pressure_psi - downstream_pressure
    return pressure_drop * ureg.psi


class FlowEquation(str, enum.Enum):
    """Enumeration of supported flow equations."""

    DARCY_WEISBACH = "Darcy-Weisbach"
    WEYMOUTH = "Weymouth"
    MODIFIED_PANHANDLE_A = "Modified Panhandle A"
    MODIFIED_PANHANDLE_B = "Modified Panhandle B"


class FlowType(str, enum.Enum):
    """Enumeration of flow types for pipes."""

    COMPRESSIBLE = "compressible"
    """Compressible flow (e.g., gases). With the flow type, the volumetric rate in pipes will vary with pressure and temperature."""
    INCOMPRESSIBLE = "incompressible"
    """Incompressible flow (e.g., liquids). The volumetric rate in pipes remains constant regardless of pressure changes."""


def determine_pipe_flow_equation(
    pressure_drop: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    length: PlainQuantity[float],
    fluid_phase: typing.Literal["liquid", "gas"],
    flow_type: FlowType,
) -> FlowEquation:
    """
    Select an appropriate flow equation based on fluid type, flow regime, pipe size, and pressure conditions.

    Rules adapted from PNG 515/516 Natural Gas Engineering II (2020/2021) table.

    :param pressure_drop: Pressure drop across the pipe (psi).
    :param upstream_pressure: Upstream absolute pressure (psi).
    :param internal_diameter: Internal diameter of the pipe (inches).
    :param length: Length of the pipe (miles).
    :param fluid_phase: Phase of the fluid, either "liquid" or "gas".
    :return: Selected flow equation from `FlowEquation` enum.
    """
    pressure_drop_ratio = (
        pressure_drop.to("psi").magnitude / upstream_pressure.to("psi").magnitude
    )
    diameter_in = internal_diameter.to("inches").magnitude
    length_miles = length.to("mile").magnitude

    # Liquids: incompressible flow → Darcy–Weisbach
    if flow_type == FlowType.INCOMPRESSIBLE or fluid_phase.lower() == "liquid":
        return FlowEquation.DARCY_WEISBACH

    # Gas: compressible flow
    if pressure_drop_ratio <= 0.1 and length_miles <= 10:
        return FlowEquation.DARCY_WEISBACH  # small ΔP → treat as incompressible

    # Long pipelines: > 20 miles
    if length_miles > 20:
        if diameter_in >= 12:  # Large diameter
            return FlowEquation.MODIFIED_PANHANDLE_A
        else:  # Smaller diameter
            return FlowEquation.MODIFIED_PANHANDLE_B

    # Short/medium pipelines
    return FlowEquation.WEYMOUTH


def compute_pipe_flow_rate(
    length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    upstream_pressure: PlainQuantity[float],
    downstream_pressure: PlainQuantity[float],
    relative_roughness: float,
    efficiency: float,
    elevation_difference: PlainQuantity[float],
    specific_gravity: float,
    temperature: PlainQuantity[float],
    compressibility_factor: float,
    reynolds_number: float,
    flow_equation: FlowEquation,
) -> PlainQuantity[float]:
    """
    Compute the flow rate in the pipe using the selected flow equation.

    :param length: Length of the pipe.
    :param internal_diameter: Internal diameter of the pipe.
    :param upstream_pressure: Upstream pressure of the pipe.
    :param downstream_pressure: Downstream pressure of the pipe.
    :param relative_roughness: Relative roughness of the pipe.
    :param efficiency: Efficiency of the pipe.
    :param elevation_difference: Elevation difference between upstream and downstream.
    :param specific_gravity: Specific gravity of the fluid.
    :param temperature: Temperature of the fluid.
    :param compressibility_factor: Compressibility factor of the fluid.
    :param reynolds_number: Reynolds number of the flow (dimensionless).
    :param flow_equation: Selected flow equation from FlowEquation enum.
    :return: Computed flow rate as a Quantity (e.g., ft³/s).
    """
    # Compute flow rate based on selected equation
    if flow_equation == FlowEquation.DARCY_WEISBACH:
        # Compute Darcy-Weisbach friction factor
        friction_factor = compute_darcy_weisbach_friction_factor(
            reynolds_number, relative_roughness=relative_roughness
        )
        return compute_darcy_weisbach_flow_rate(
            length=length,
            internal_diameter=internal_diameter,
            upstream_pressure=upstream_pressure,
            downstream_pressure=downstream_pressure,
            specific_gravity=specific_gravity,
            friction_factor=friction_factor,
        )

    elif flow_equation == FlowEquation.WEYMOUTH:
        return compute_weymouth_flow_rate(
            pipeline_length=length,
            internal_diameter=internal_diameter,
            upstream_pressure=upstream_pressure,
            downstream_pressure=downstream_pressure,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )

    elif flow_equation == FlowEquation.MODIFIED_PANHANDLE_A:
        return compute_modified_panhandle_A_flow_rate(
            pipeline_length=length,
            internal_diameter=internal_diameter,
            upstream_pressure=upstream_pressure,
            downstream_pressure=downstream_pressure,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )
    elif flow_equation == FlowEquation.MODIFIED_PANHANDLE_B:
        return compute_modified_panhandle_B_flow_rate(
            pipeline_length=length,
            internal_diameter=internal_diameter,
            upstream_pressure=upstream_pressure,
            downstream_pressure=downstream_pressure,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )

    raise ValueError(f"Unsupported flow equation: {flow_equation}")


def compute_pipe_pressure_drop(
    upstream_pressure: PlainQuantity[float],
    length: PlainQuantity[float],
    internal_diameter: PlainQuantity[float],
    relative_roughness: float,
    efficiency: float,
    elevation_difference: PlainQuantity[float],
    specific_gravity: float,
    temperature: PlainQuantity[float],
    compressibility_factor: float,
    density: PlainQuantity[float],
    viscosity: PlainQuantity[float],
    flow_rate: PlainQuantity[float],
    flow_equation: FlowEquation,
) -> PlainQuantity[float]:
    """
    Compute the pressure drop in the pipe using the selected flow equation and given flow rate.

    :param upstream_pressure: Upstream pressure of the pipe.
    :param length: Length of the pipe.
    :param internal_diameter: Internal diameter of the pipe.
    :param relative_roughness: Relative roughness of the pipe.
    :param efficiency: Efficiency of the pipe.
    :param elevation_difference: Elevation difference between upstream and downstream.
    :param specific_gravity: Specific gravity of the fluid.
    :param temperature: Temperature of the fluid.
    :param compressibility_factor: Compressibility factor of the fluid.
    :param density: Density of the fluid.
    :param viscosity: Dynamic viscosity of the fluid.
    :param flow_rate: Flow rate through the pipe as a Quantity (e.g., ft³/s).
    :param flow_equation: Selected flow equation from FlowEquation enum.
    :return: Computed pressure drop as a Quantity (psi).
    """
    if flow_equation == FlowEquation.DARCY_WEISBACH:
        # Calculate Reynolds number for friction factor
        reynolds_number = compute_reynolds_number(
            current_flow_rate=flow_rate,
            pipe_internal_diameter=internal_diameter,
            fluid_density=density,
            fluid_dynamic_viscosity=viscosity,
        )
        # Compute Darcy-Weisbach friction factor
        friction_factor = compute_darcy_weisbach_friction_factor(
            reynolds_number, relative_roughness=relative_roughness
        )
        return compute_darcy_weisbach_pressure_drop(
            flow_rate=flow_rate,
            length=length,
            internal_diameter=internal_diameter,
            specific_gravity=specific_gravity,
            friction_factor=friction_factor,
        )

    elif flow_equation == FlowEquation.WEYMOUTH:
        return compute_weymouth_pressure_drop(
            upstream_pressure=upstream_pressure,
            flow_rate=flow_rate,
            pipeline_length=length,
            internal_diameter=internal_diameter,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )

    elif flow_equation == FlowEquation.MODIFIED_PANHANDLE_A:
        return compute_modified_panhandle_A_pressure_drop(
            upstream_pressure=upstream_pressure,
            flow_rate=flow_rate,
            pipeline_length=length,
            internal_diameter=internal_diameter,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )

    elif flow_equation == FlowEquation.MODIFIED_PANHANDLE_B:
        return compute_modified_panhandle_B_pressure_drop(
            upstream_pressure=upstream_pressure,
            flow_rate=flow_rate,
            pipeline_length=length,
            internal_diameter=internal_diameter,
            gas_specific_gravity=specific_gravity,
            average_temperature=temperature,
            compressibility_factor=compressibility_factor,
            pipeline_efficiency=efficiency,
            elevation_difference=elevation_difference,
        )

    raise ValueError(f"Unsupported flow equation: {flow_equation!r}")


def compute_tapered_pipe_pressure_drop(
    flow_rate: PlainQuantity[float],
    pipe_inlet_diameter: PlainQuantity[float],
    pipe_outlet_diameter: PlainQuantity[float],
    pipe_length: PlainQuantity[float],
    fluid_density: PlainQuantity[float],
    fluid_dynamic_viscosity: PlainQuantity[float],
    pipe_relative_roughness: float = 0.0,
    gradual_angle_threshold_deg: float = 30.0,
) -> PlainQuantity[float]:
    """
    Calculate the pressure drop across a tapered pipe (reducer or expander).

    - If taper angle < gradual_angle_threshold_deg → treat as gradual.
    - Otherwise → treat as sudden (use Borda-Carnot or empirical contraction).

    Uses Darcy-Weisbach for distributed losses and adds local losses
    depending on geometry.

    :param flow_rate: Volumetric flow rate of the fluid (e.g., m^3/s)
    :param pipe_inlet_diameter: Internal diameter at the pipe inlet (e.g., m)
    :param pipe_outlet_diameter: Internal diameter at the pipe outlet (e.g., m)
    :param pipe_length: Length of the tapered section (e.g., m)
    :param fluid_density: Fluid density (e.g., kg/m^3)
    :param fluid_dynamic_viscosity: Fluid dynamic viscosity (e.g., Pa·s)
    :param pipe_relative_roughness: Relative roughness of the pipe (dimensionless, default 0.0)
    :return: Pressure drop across the tapered pipe in psi (as a Pint Quantity).
    """
    pipe_inlet_diameter_m = pipe_inlet_diameter.to("m").magnitude
    pipe_outlet_diameter_m = pipe_outlet_diameter.to("m").magnitude
    pipe_length_m = pipe_length.to("m").magnitude
    fluid_density_kg_per_m3 = fluid_density.to("kg/m^3").magnitude

    # Areas & velocities
    area_inlet_m2 = math.pi * (pipe_inlet_diameter_m**2) / 4
    area_outlet_m2 = math.pi * (pipe_outlet_diameter_m**2) / 4
    velocity_inlet_m_per_s = flow_rate.to("m^3/s").magnitude / area_inlet_m2
    velocity_outlet_m_per_s = flow_rate.to("m^3/s").magnitude / area_outlet_m2
    average_velocity_m_per_s = (velocity_inlet_m_per_s + velocity_outlet_m_per_s) / 2
    average_pipe_diameter_m = (pipe_inlet_diameter_m + pipe_outlet_diameter_m) / 2

    # Reynolds number
    reynolds_number = compute_reynolds_number(
        current_flow_rate=flow_rate,
        pipe_internal_diameter=Quantity(average_pipe_diameter_m, "m"),
        fluid_density=fluid_density,
        fluid_dynamic_viscosity=fluid_dynamic_viscosity,
    )
    friction_factor = compute_darcy_weisbach_friction_factor(
        reynolds_number=reynolds_number, relative_roughness=pipe_relative_roughness
    )

    # Frictional ΔP
    frictional_pressure_drop_pa = (
        friction_factor
        * (pipe_length_m / average_pipe_diameter_m)
        * 0.5
        * fluid_density_kg_per_m3
        * average_velocity_m_per_s**2
    )

    # Compute taper angle
    delta_diameter = abs(pipe_outlet_diameter_m - pipe_inlet_diameter_m)
    taper_angle_deg = math.degrees(math.atan(delta_diameter / (2 * pipe_length_m)))

    # Local loss coefficient
    if pipe_outlet_diameter_m > pipe_inlet_diameter_m:
        # Expansion
        if taper_angle_deg <= gradual_angle_threshold_deg:
            # Gradual expansion (Crane TP-410: K = (1 - A_in/A_out)^2 * (sin θ / θ))
            local_loss_coefficient = (1 - area_inlet_m2 / area_outlet_m2) ** 2 * (
                math.sin(math.radians(taper_angle_deg)) / math.radians(taper_angle_deg)
            )
        else:
            # Sudden expansion (Borda-Carnot)
            local_loss_coefficient = (1 - area_inlet_m2 / area_outlet_m2) ** 2
        local_pressure_drop_pa = (
            local_loss_coefficient
            * 0.5
            * fluid_density_kg_per_m3
            * velocity_outlet_m_per_s**2
        )
    else:
        # Contraction
        if taper_angle_deg <= gradual_angle_threshold_deg:
            # Gradual contraction (use conservative low-loss coefficient)
            local_loss_coefficient = 0.1  # Crane gives ~0.04–0.2 depending on angle
        else:
            # Sudden contraction (empirical)
            local_loss_coefficient = (
                0.5 * (1 - (area_outlet_m2 / area_inlet_m2)) ** 0.75
            )
        local_pressure_drop_pa = (
            local_loss_coefficient
            * 0.5
            * fluid_density_kg_per_m3
            * velocity_inlet_m_per_s**2
        )

    # Total ΔP
    total_pressure_drop_pa = (
        frictional_pressure_drop_pa + local_pressure_drop_pa
    ) * ureg.Pa
    return total_pressure_drop_pa.to("psi")  # type: ignore


# def compute_tapered_pipe_pressure_drop(
#     flow_rate: PlainQuantity[float],
#     pipe_inlet_diameter: PlainQuantity[float],
#     pipe_outlet_diameter: PlainQuantity[float],
#     pipe_length: PlainQuantity[float],
#     fluid_density: PlainQuantity[float],
#     fluid_dynamic_viscosity: PlainQuantity[float],
#     pipe_relative_roughness: float = 0.0,
# ) -> PlainQuantity[float]:
#     """
#     Calculate the pressure drop across a tapered (reducer or expander) pipe using
#     the Darcy-Weisbach equation for frictional losses and additional local
#     loss coefficients for gradual contraction or expansion.

#     The formula used combines frictional losses along the tapered length and
#     local losses due to the change in diameter:

#         ΔP_friction = f * (L/D_avg) * (ρ * V_avg^2 / 2)

#         ΔP_local = K * (ρ * V_out^2 / 2)

#         Total ΔP = ΔP_friction + ΔP_local
#     where:
#         - f is the Darcy-Weisbach friction factor (dimensionless)
#         - L is the length of the tapered section (m)
#         - D_avg is the average diameter of the pipe (m)
#         - ρ is the fluid density (kg/m^3)
#         - V_avg is the average velocity in the tapered section (m/s)
#         - K is the local loss coefficient (dimensionless)
#         - V_out is the velocity at the outlet of the tapered section (m/s)
#         - ΔP is the pressure drop (Pa)
#         - D_avg = (D_inlet + D_outlet) / 2
#         - V_avg = (V_inlet + V_outlet) / 2
#         - For gradual expansion: K = (1 - (A_inlet / A_outlet))^2
#         - For gradual contraction: K = 0.5 * (1 - (A_outlet / A_inlet))^0.75

#     :param flow_rate: Volumetric flow rate of the fluid (e.g., m^3/s)
#     :param pipe_inlet_diameter: Internal diameter at the pipe inlet (e.g., m)
#     :param pipe_outlet_diameter: Internal diameter at the pipe outlet (e.g., m)
#     :param pipe_length: Length of the tapered section (e.g., m)
#     :param fluid_density: Fluid density (e.g., kg/m^3)
#     :param fluid_dynamic_viscosity: Fluid dynamic viscosity (e.g., Pa·s)
#     :param pipe_relative_roughness: Relative roughness of the pipe (dimensionless, default 0.0)
#     :return: Pressure drop across the tapered pipe in psi (as a Pint Quantity).
#     """
#     # Convert to SI units
#     pipe_inlet_diameter_m = pipe_inlet_diameter.to("m").magnitude
#     pipe_outlet_diameter_m = pipe_outlet_diameter.to("m").magnitude
#     pipe_length_m = pipe_length.to("m").magnitude
#     fluid_density_kg_per_m3 = fluid_density.to("kg/m^3").magnitude

#     # Cross-sectional areas and average velocities
#     area_inlet_m2 = math.pi * (pipe_inlet_diameter_m**2) / 4
#     area_outlet_m2 = math.pi * (pipe_outlet_diameter_m**2) / 4
#     velocity_inlet_m_per_s = flow_rate.to("m^3/s").magnitude / area_inlet_m2
#     velocity_outlet_m_per_s = flow_rate.to("m^3/s").magnitude / area_outlet_m2

#     # Average diameter and velocity for friction along taper
#     average_pipe_diameter_m = (pipe_inlet_diameter_m + pipe_outlet_diameter_m) / 2
#     average_velocity_m_per_s = (velocity_inlet_m_per_s + velocity_outlet_m_per_s) / 2

#     # Reynolds number at inlet
#     reynolds_number = compute_reynolds_number(
#         current_flow_rate=flow_rate,
#         pipe_internal_diameter=Quantity(average_pipe_diameter_m, "m"),
#         fluid_density=fluid_density,
#         fluid_dynamic_viscosity=fluid_dynamic_viscosity,
#     )

#     # Darcy-Weisbach friction factor
#     friction_factor = compute_darcy_weisbach_friction_factor(
#         reynolds_number=reynolds_number, relative_roughness=pipe_relative_roughness
#     )

#     # Frictional pressure drop along tapered length
#     frictional_pressure_drop_pa = (
#         friction_factor
#         * (pipe_length_m / average_pipe_diameter_m)
#         * 0.5
#         * fluid_density_kg_per_m3
#         * average_velocity_m_per_s**2
#     )

#     # Local loss coefficient for expansion or contraction
#     if pipe_outlet_diameter_m > pipe_inlet_diameter_m:
#         # Gradual expansion
#         local_loss_coefficient = (1 - (area_inlet_m2 / area_outlet_m2)) ** 2
#         local_pressure_drop_pa = (
#             local_loss_coefficient
#             * 0.5
#             * fluid_density_kg_per_m3
#             * velocity_outlet_m_per_s**2
#         )
#     else:
#         # Gradual contraction
#         local_loss_coefficient = 0.5 * (1 - (area_outlet_m2 / area_inlet_m2)) ** 0.75
#         local_pressure_drop_pa = (
#             local_loss_coefficient
#             * 0.5
#             * fluid_density_kg_per_m3
#             * velocity_inlet_m_per_s**2
#         )

#     # Total pressure drop in Pa
#     total_pressure_drop_pa = (
#         frictional_pressure_drop_pa + local_pressure_drop_pa
#     ) * ureg.Pa
#     # Convert to psi
#     total_pressure_drop_psi = total_pressure_drop_pa.to("psi")  # type: ignore
#     return total_pressure_drop_psi
