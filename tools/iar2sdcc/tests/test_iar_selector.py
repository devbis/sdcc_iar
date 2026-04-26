import tempfile
import unittest
from pathlib import Path

from iar2sdcc.models import ModuleRecord
from iar2sdcc.overrides import load_forced_modules
from iar2sdcc.selector import select_modules


class SelectorTest(unittest.TestCase):
    def test_selects_only_modules_needed_by_symbols(self) -> None:
        modules = [
            ModuleRecord(name="AddrMgr", exports=["_AddrMgrInit"], imports=[]),
            ModuleRecord(name="Unused", exports=["_Unused"], imports=[]),
        ]
        selected = select_modules(modules, needed_symbols={"_AddrMgrInit"}, forced_modules=set())
        self.assertEqual([m.name for m in selected], ["AddrMgr"])

    def test_loads_forced_modules_from_override_list(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "forced.yaml"
            path.write_text("# comment\n- AddrMgr\n- mac_beacon\n", encoding="utf-8")
            self.assertEqual(load_forced_modules(path), {"AddrMgr", "mac_beacon"})

