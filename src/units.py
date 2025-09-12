from pint import UnitRegistry

ureg = UnitRegistry()
ureg.define("scf = 0.0283168 * meter**3 = SCF")  # 1 scf ≈ 0.0283168 m³
ureg.define("Mscf = 1000 * scf = MSCf")  # 1 Mscf = 1000 scf
ureg.define("MMscf = 1000 * Mscf = MMSCF")  # 1 MMscf = 1,000,000 scf
ureg.define("MMMscf = 1000 * MMscf = MMMSCF")  # 1 MMMSCF = 1,000,000,000 scf
Quantity = ureg.Quantity
Unit = ureg.Unit
