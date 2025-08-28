from pint import UnitRegistry

ureg = UnitRegistry()
ureg.define("scf = 0.0283168 * meter**3 = SCF")  # 1 scf ≈ 0.0283168 m³
Quantity = ureg.Quantity
