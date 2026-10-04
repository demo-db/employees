import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rebuild_source", ROOT / "scripts" / "rebuild-source.py")
REBUILD = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(REBUILD)


class InsertDumpTests(unittest.TestCase):
    def test_multiple_insert_statements_and_mysql_escapes_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "employees.dump"
            path.write_text(
                "INSERT INTO `employees` VALUES (1,'O\\'Neil','A\\\\B',NULL);\n"
                "INSERT INTO `employees` VALUES (2,'München','line\\nfeed','x');\n",
                encoding="utf-8",
            )
            rows = list(REBUILD.parse_insert_dump(path, "employees", 4))
        self.assertEqual(rows, [(1, "O'Neil", "A\\B", None), (2, "München", "line\nfeed", "x")])

    def test_invalid_or_incomplete_dump_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "employees.dump"
            path.write_text("INSERT INTO employees VALUES (1,'incomplete');", encoding="utf-8")
            with self.assertRaises(REBUILD.BuildError):
                list(REBUILD.parse_insert_dump(path, "employees", 3))
            path.write_text("INSERT INTO employees VALUES (1,'unterminated);", encoding="utf-8")
            with self.assertRaises(REBUILD.BuildError):
                list(REBUILD.parse_insert_dump(path, "employees", 2))


if __name__ == "__main__":
    unittest.main()
