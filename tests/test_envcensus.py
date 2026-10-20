import json
import tempfile
import unittest
from pathlib import Path

from envcensus.cli import main
from envcensus.scan import analyze, load_config, scan


def make(files):
    d = Path(tempfile.mkdtemp())
    for name, text in files.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return d


def run(files):
    d = make(files)
    cfg = load_config(d, None)
    return analyze(scan(d, cfg), cfg)


class ScanTests(unittest.TestCase):
    def test_detects_reads_across_languages(self):
        r = run({
            "a.py": 'import os\nos.environ["PY_VAR"]\nos.getenv("PY_GET")\n',
            "b.ts": 'const a = process.env.TS_VAR; const b = import.meta.env.VITE_KEY;\n',
            "c.go": 'os.Getenv("GO_VAR")\n',
            "d.rs": 'std::env::var("RS_VAR")\n',
            "e.rb": 'ENV.fetch("RB_VAR")\n',
            "f.sh": 'echo "${SH_VAR:-x}"\n',
        })
        for v in ["PY_VAR", "PY_GET", "TS_VAR", "VITE_KEY", "GO_VAR", "RS_VAR", "RB_VAR", "SH_VAR"]:
            self.assertIn(v, r["undocumented"], v)

    def test_shell_local_assignments_not_external(self):
        r = run({"x.sh": 'WORK=/tmp/x\nfor CLI in a b; do echo "$CLI $WORK $REAL_INPUT"; done\n'})
        self.assertEqual(list(r["undocumented"]), ["REAL_INPUT"])

    def test_documented_not_flagged(self):
        r = run({"a.py": 'os.getenv("API_URL")', ".env.example": "API_URL=http://x\n"})
        self.assertEqual(r["undocumented"], {})
        self.assertEqual(r["unused"], {})

    def test_unused_documented(self):
        r = run({".env.example": "STALE_KEY=1\n# COMMENTED_KEY=2\n", "a.py": "x = 1\n"})
        self.assertIn("STALE_KEY", r["unused"])
        self.assertIn("COMMENTED_KEY", r["unused"])

    def test_readme_counts_as_documentation(self):
        r = run({"a.py": 'os.getenv("DOC_IN_README")', "README.md": "Set `DOC_IN_README`.\n"})
        self.assertEqual(r["undocumented"], {})

    def test_default_ignores_and_excludes(self):
        r = run({"a.py": 'os.getenv("HOME"); os.getenv("GITHUB_TOKEN")',
                 "node_modules/x.js": "process.env.HIDDEN_VAR"})
        self.assertEqual(r["undocumented"], {})

    def test_not_in_ci(self):
        r = run({"a.py": 'os.getenv("DB_URL")', ".env.example": "DB_URL=\n",
                 ".github/workflows/ci.yml": "env:\n  OTHER: 1\n"})
        self.assertEqual(r["not_in_ci"], ["DB_URL"])

    def test_lowercase_and_dynamic_names_ignored(self):
        r = run({"a.py": 'os.getenv(name)\nos.getenv("lower")\n'})
        self.assertEqual(r["undocumented"], {})

    def test_binary_file_skipped(self):
        d = make({"a.py": 'os.getenv("OK_VAR")'})
        (d / "b.py").write_bytes(b"\xff\xfe\x00bad")
        cfg = load_config(d, None)
        self.assertIn("OK_VAR", analyze(scan(d, cfg), cfg)["undocumented"])


class CliTests(unittest.TestCase):
    def test_exit_codes(self):
        d = make({"a.py": 'os.getenv("NEW_VAR")'})
        self.assertEqual(main([str(d)]), 1)
        self.assertEqual(main([str(d), "--fail-on", "none"]), 0)
        self.assertEqual(main([str(d / "missing")]), 2)

    def test_bad_config(self):
        d = make({"a.py": "x=1", "envcensus.json": "{not json"})
        self.assertEqual(main([str(d)]), 2)

    def test_custom_config_ignore(self):
        d = make({"a.py": 'os.getenv("MY_VAR")', "envcensus.json": json.dumps({"ignore_vars": ["MY_*"]})})
        self.assertEqual(main([str(d)]), 0)

    def test_clean_project_exit_zero(self):
        d = make({"a.py": 'os.getenv("OK")', ".env.example": "OK=1\n"})
        self.assertEqual(main([str(d)]), 0)


if __name__ == "__main__":
    unittest.main()
