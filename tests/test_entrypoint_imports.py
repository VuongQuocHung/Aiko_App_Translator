import subprocess
import sys
import unittest
from pathlib import Path


class EntrypointImportTests(unittest.TestCase):
    def test_glossary_modules_import_independently(self):
        root = Path(__file__).resolve().parents[1]
        for module in ("cores.translation.prompts", "cores.context.validation", "cores.postprocess.glossary", "cores.stages.budget"):
            with self.subTest(module=module):
                result = subprocess.run([sys.executable, "-X", "utf8", "-c", f"import {module}; print('import-ok')"],
                                        cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=15)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("import-ok", result.stdout)

    def test_context_entrypoint_imports_in_a_clean_process(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import cores.context.__main__; print('context-import-ok')",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("context-import-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
