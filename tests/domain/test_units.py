"""Tests for flowline_scada.domain.units."""

import attrs
import pint
import pytest

from flowline_scada.domain.units import (
    IMPERIAL,
    OIL_FIELD,
    SI,
    Quantity,
    QuantityUnit,
    Unit,
    UnitSystem,
    ureg,
)

# Every quantity name the built-in unit systems are expected to define.
# Used both to check completeness and to drive parametrized checks below.
EXPECTED_QUANTITY_NAMES: tuple[str, ...] = (
    "length",
    "diameter",
    "pressure",
    "temperature",
    "flow_rate",
    "mass_flow_rate",
    "flow_volume",
    "molecular_weight",
    "roughness",
    "elevation",
    "area",
    "velocity",
    "density",
    "viscosity",
)

# Quantity names that ship with a non-None default value in every built-in
# unit system, and the ones that deliberately don't.
NAMES_WITH_DEFAULTS: frozenset[str] = frozenset({"temperature", "molecular_weight", "elevation"})
NAMES_WITHOUT_DEFAULTS: frozenset[str] = frozenset(EXPECTED_QUANTITY_NAMES) - NAMES_WITH_DEFAULTS


def _default_quantity(quantity_unit: QuantityUnit) -> "pint.Quantity[float]":
    """Build a Quantity from a QuantityUnit's default, asserting it's
    actually set first. Every call site below is for a quantity name in
    NAMES_WITH_DEFAULTS, so a None default here would itself be the bug
    under test, not something to silently paper over — and asserting
    narrows the type from `float | None` to `float` for mypy, which is
    the actual reason this exists rather than inlining `Quantity(x.default,
    x.unit)` at each call site.
    """
    assert quantity_unit.default is not None, f"expected a non-None default on {quantity_unit!r}"
    return Quantity(quantity_unit.default, quantity_unit.unit)


class TestCustomUnitDefinitions:
    """The gas-volume units (scf/Mscf/MMscf/MMMscf) are registered by this
    module as a side effect of import, not built into pint — worth pinning
    down that the conversion factors are actually correct, not just that
    the names resolve."""

    def test_scf_converts_to_cubic_meters(self) -> None:
        one_scf = Quantity(1, "scf")
        assert one_scf.to("m^3").magnitude == pytest.approx(0.0283168, rel=1e-6)

    def test_mscf_is_one_thousand_scf(self) -> None:
        one_mscf = Quantity(1, "Mscf")
        assert one_mscf.to("scf").magnitude == pytest.approx(1000.0, rel=1e-9)

    def test_mmscf_is_one_million_scf(self) -> None:
        one_mmscf = Quantity(1, "MMscf")
        assert one_mmscf.to("scf").magnitude == pytest.approx(1_000_000.0, rel=1e-9)

    def test_mmmscf_is_one_billion_scf(self) -> None:
        one_mmmscf = Quantity(1, "MMMscf")
        assert one_mmmscf.to("scf").magnitude == pytest.approx(1_000_000_000.0, rel=1e-9)

    def test_quantity_and_unit_are_bound_to_the_shared_registry(self) -> None:
        # Quantity/Unit must come from the same UnitRegistry instance that
        # scf/Mscf/etc were defined on, or a Quantity built via Quantity(...)
        # wouldn't recognize those unit strings at all.
        assert Quantity(1, "scf")._REGISTRY is ureg
        assert Unit("scf")._REGISTRY is ureg


class TestQuantityUnit:
    def test_str_uses_display_when_provided(self) -> None:
        qu = QuantityUnit(unit="degF", display="°F")
        assert str(qu) == "°F"

    def test_str_falls_back_to_unit_when_no_display(self) -> None:
        qu = QuantityUnit(unit="psi")
        assert str(qu) == str(Unit("psi"))

    def test_default_is_none_unless_specified(self) -> None:
        qu = QuantityUnit(unit="ft")
        assert qu.default is None

    def test_default_is_preserved_when_specified(self) -> None:
        qu = QuantityUnit(unit="degF", default=60.0)
        assert qu.default == 60.0

    def test_unit_field_accepts_a_unit_string(self) -> None:
        qu = QuantityUnit(unit="psi")
        assert qu.unit == Unit("psi")

    def test_is_frozen(self) -> None:
        qu = QuantityUnit(unit="psi")
        with pytest.raises(attrs.exceptions.FrozenInstanceError):
            qu.default = 100.0  # type: ignore[misc]


class TestUnitSystemBasics:
    def test_missing_key_returns_dimensionless_default(
        self, empty_unit_system: UnitSystem[QuantityUnit]
    ) -> None:
        fallback = empty_unit_system["nonexistent_quantity"]
        assert fallback.unit == Unit("dimensionless")
        assert fallback.default is None

    def test_missing_key_does_not_raise(self, empty_unit_system: UnitSystem[QuantityUnit]) -> None:
        # The whole point of subclassing defaultdict here: UI code doing a
        # lookup-by-name for a quantity a system hasn't defined shouldn't
        # have to handle KeyError.
        try:
            empty_unit_system["anything"]
        except KeyError:
            pytest.fail("UnitSystem raised KeyError instead of using the default factory")

    def test_name_is_stored(self) -> None:
        system: UnitSystem[QuantityUnit] = UnitSystem("custom")
        assert system.name == "custom"

    def test_str_includes_class_and_name(self) -> None:
        system: UnitSystem[QuantityUnit] = UnitSystem("custom")
        assert str(system) == "UnitSystem(custom)"

    def test_repr_includes_name_and_units(self) -> None:
        system: UnitSystem[QuantityUnit] = UnitSystem(
            "custom", {"pressure": QuantityUnit(unit="psi")}
        )
        text = repr(system)
        assert "custom" in text
        assert "pressure" in text

    def test_initial_mapping_is_populated(self) -> None:
        system: UnitSystem[QuantityUnit] = UnitSystem(
            "custom", {"pressure": QuantityUnit(unit="psi", default=14.7)}
        )
        assert system["pressure"].unit == Unit("psi")
        assert system["pressure"].default == 14.7

    def test_kwargs_are_merged_with_initial_mapping(self) -> None:
        system: UnitSystem[QuantityUnit] = UnitSystem(
            "custom",
            {"pressure": QuantityUnit(unit="psi")},
            temperature=QuantityUnit(unit="degF"),
        )
        assert system["pressure"].unit == Unit("psi")
        assert system["temperature"].unit == Unit("degF")

    def test_custom_default_factory_is_used_for_missing_keys(self) -> None:
        sentinel = QuantityUnit(unit="m", display="sentinel")
        system: UnitSystem[QuantityUnit] = UnitSystem("custom", default_factory=lambda: sentinel)
        assert system["whatever"] is sentinel


class TestBuiltinUnitSystems:
    """Shared invariants that should hold for every built-in unit system —
    parametrized over IMPERIAL/SI/OIL_FIELD via the `unit_system` fixture,
    so a gap in any one of them fails on its own rather than needing three
    near-duplicate test functions."""

    @pytest.mark.parametrize("name", EXPECTED_QUANTITY_NAMES)
    def test_defines_every_expected_quantity(
        self, unit_system: UnitSystem[QuantityUnit], name: str
    ) -> None:
        assert name in unit_system, (
            f"{unit_system.name!r} unit system is missing a definition for {name!r}"
        )

    @pytest.mark.parametrize("name", EXPECTED_QUANTITY_NAMES)
    def test_every_quantity_has_a_pint_compatible_unit(
        self, unit_system: UnitSystem[QuantityUnit], name: str
    ) -> None:
        # Constructing a Quantity with each system's declared unit string is
        # a stronger check than just "the attribute is set" — it proves
        # pint actually recognizes the unit (catches typos like a unit
        # string that doesn't parse).
        quantity_unit = unit_system[name]
        constructed = Quantity(1.0, quantity_unit.unit)
        assert constructed.units == quantity_unit.unit

    @pytest.mark.parametrize("name", sorted(NAMES_WITH_DEFAULTS))
    def test_quantities_that_should_have_defaults_do(
        self, unit_system: UnitSystem[QuantityUnit], name: str
    ) -> None:
        assert unit_system[name].default is not None, (
            f"{unit_system.name!r}.{name} should have a non-None default"
        )

    @pytest.mark.parametrize("name", sorted(NAMES_WITHOUT_DEFAULTS))
    def test_quantities_that_should_not_have_defaults_dont(
        self, unit_system: UnitSystem[QuantityUnit], name: str
    ) -> None:
        assert unit_system[name].default is None, (
            f"{unit_system.name!r}.{name} unexpectedly has a default "
            f"({unit_system[name].default!r}) — update NAMES_WITH_DEFAULTS "
            "in this test if that's intentional"
        )

    def test_all_three_systems_are_distinct_objects(self) -> None:
        assert IMPERIAL is not SI
        assert SI is not OIL_FIELD
        assert IMPERIAL is not OIL_FIELD


class TestUnitSystemPhysicalConsistency:
    """Cross-checks that the three systems actually agree on the physical
    quantity a given default represents, just expressed in each system's
    own unit — catches the specific class of bug where someone updates one
    system's default and forgets the others exist."""

    def test_default_temperatures_agree_across_systems(self) -> None:
        imperial_temp = _default_quantity(IMPERIAL["temperature"])
        si_temp = _default_quantity(SI["temperature"])
        oil_field_temp = _default_quantity(OIL_FIELD["temperature"])

        assert imperial_temp.to("degC").magnitude == pytest.approx(
            si_temp.to("degC").magnitude, abs=0.5
        )
        assert oil_field_temp.to("degC").magnitude == pytest.approx(
            si_temp.to("degC").magnitude, abs=0.5
        )

    def test_default_molecular_weight_agrees_across_systems(self) -> None:
        # All three default to methane's molecular weight — same value,
        # same unit (g/mol) in every system, so this should match exactly
        # rather than needing a unit conversion first.
        assert IMPERIAL["molecular_weight"].default == SI["molecular_weight"].default
        assert SI["molecular_weight"].default == OIL_FIELD["molecular_weight"].default

    def test_default_elevations_agree_across_systems(self) -> None:
        imperial_elev = _default_quantity(IMPERIAL["elevation"])
        si_elev = _default_quantity(SI["elevation"])

        assert imperial_elev.to("m").magnitude == pytest.approx(si_elev.to("m").magnitude, abs=1e-9)
