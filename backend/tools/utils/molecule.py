class Molecule:
    def __init__(self, name: str, atoms: list = None):
        self.name = name
        self.atoms = atoms or []

    def to_xyz(self) -> str:
        lines = [str(len(self.atoms)), self.name]
        for atom in self.atoms:
            lines.append(f"{atom['symbol']} {atom['x']} {atom['y']} {atom['z']}")
        return "\n".join(lines)
