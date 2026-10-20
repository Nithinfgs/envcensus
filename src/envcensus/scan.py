"""Find environment variable reads in source code and declarations in config files."""
from __future__ import annotations

import fnmatch
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

NAME = r"([A-Z][A-Z0-9_]{1,})"
Q = r"""['"]"""

# (compiled regex, languages) -- every pattern captures the variable name in group 1.
CODE_PATTERNS = [
    re.compile(rf"os\.environ\s*\[\s*{Q}{NAME}{Q}\s*\]"),
    re.compile(rf"os\.environ\.get\(\s*{Q}{NAME}{Q}"),
    re.compile(rf"os\.getenv\(\s*{Q}{NAME}{Q}"),
    re.compile(rf"process\.env\.{NAME}\b"),
    re.compile(rf"process\.env\[\s*{Q}{NAME}{Q}\s*\]"),
    re.compile(rf"import\.meta\.env\.{NAME}\b"),
    re.compile(rf"Deno\.env\.get\(\s*{Q}{NAME}{Q}"),
    re.compile(rf"os\.(?:Getenv|LookupEnv)\(\s*\"{NAME}\""),
    re.compile(rf"(?:std::)?env::var(?:_os)?\(\s*\"{NAME}\""),
    re.compile(rf"ENV(?:\.fetch)?[\[\(]\s*{Q}{NAME}{Q}"),
    re.compile(rf"System\.getenv\(\s*\"{NAME}\""),
    re.compile(rf"getenv\(\s*{Q}{NAME}{Q}"),
]
SHELL_PATTERN = re.compile(r"\$\{?([A-Z][A-Z0-9_]{1,})(?::?[-=?+][^}]*)?\}?")

# Names a script assigns itself (VAR=, export VAR=, local VAR=, for VAR in) are not external inputs.
SHELL_ASSIGN = re.compile(r"(?:^|[\s;])(?:export\s+|local\s+|readonly\s+|declare\s+(?:-\w+\s+)?)?([A-Z][A-Z0-9_]+)=|\bfor\s+([A-Z][A-Z0-9_]+)\s+in\b", re.M)

CODE_EXTS = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".go", ".rs",
             ".rb", ".java", ".kt", ".php", ".vue", ".svelte"}
SHELL_EXTS = {".sh", ".bash", ".zsh"}

DEFAULT_EXCLUDES = {"node_modules", ".git", "vendor", "dist", "build", ".venv",
                    "venv", "__pycache__", "target", ".next"}
DEFAULT_IGNORE = ["HOME", "PATH", "PWD", "USER", "SHELL", "TERM", "LANG", "TMPDIR",
                  "CI", "GITHUB_*", "RUNNER_*", "NODE_ENV", "PYTHONPATH", "HOSTNAME"]

ENV_FILE_NAMES = (".env.example", ".env.sample", ".env.template", ".env.dist")
ASSIGN = re.compile(rf"^\s*(?:export\s+)?{NAME}\s*=", re.M)
COMMENTED_ASSIGN = re.compile(rf"^\s*#\s*{NAME}\s*=", re.M)


@dataclass
class Census:
    reads: dict = field(default_factory=dict)      # var -> [(file, line)]
    documented: dict = field(default_factory=dict)  # var -> [file]
    ci_set: dict = field(default_factory=dict)      # var -> [file]
    compose_set: dict = field(default_factory=dict)
    readme: dict = field(default_factory=dict)


def load_config(root: Path, path: str | None) -> dict:
    cfg = {"ignore_vars": list(DEFAULT_IGNORE), "exclude_dirs": sorted(DEFAULT_EXCLUDES)}
    candidate = Path(path) if path else root / "envcensus.json"
    if candidate.exists():
        try:
            data = json.loads(candidate.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"cannot read config {candidate}: {exc}") from exc
        for key in ("ignore_vars", "exclude_dirs"):
            if key in data:
                cfg[key] = list(data[key])
    elif path:
        raise ValueError(f"config file not found: {path}")
    return cfg


def is_ignored(name: str, patterns) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in patterns)


def walk(root: Path, excludes):
    for p in sorted(root.rglob("*")):
        if any(part in excludes for part in p.relative_to(root).parts[:-1]):
            continue
        if p.is_file():
            yield p


def read_text(p: Path) -> str | None:
    try:
        if p.stat().st_size > 2_000_000:
            return None
        return p.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeDecodeError):
        return None


def _add(d: dict, key: str, val) -> None:
    d.setdefault(key, [])
    if val not in d[key]:
        d[key].append(val)


def scan(root: Path, cfg: dict) -> Census:
    c = Census()
    excludes = set(cfg["exclude_dirs"])
    for p in walk(root, excludes):
        rel = str(p.relative_to(root))
        name = p.name
        text = None
        if name in ENV_FILE_NAMES or name.endswith(".env.example"):
            text = read_text(p)
            if text:
                for m in ASSIGN.finditer(text):
                    _add(c.documented, m.group(1), rel)
                for m in COMMENTED_ASSIGN.finditer(text):
                    _add(c.documented, m.group(1), rel)
        elif p.suffix in CODE_EXTS:
            text = read_text(p)
            if text:
                for lineno, line in enumerate(text.splitlines(), 1):
                    for pat in CODE_PATTERNS:
                        for m in pat.finditer(line):
                            _add(c.reads, m.group(1), (rel, lineno))
        elif p.suffix in SHELL_EXTS:
            text = read_text(p)
            if text:
                local = {n for pair in SHELL_ASSIGN.findall(text) for n in pair if n}
                for lineno, line in enumerate(text.splitlines(), 1):
                    if line.lstrip().startswith("#"):
                        continue
                    for m in SHELL_PATTERN.finditer(line):
                        if m.group(1) not in local:
                            _add(c.reads, m.group(1), (rel, lineno))
        elif rel.startswith(".github/workflows/") and p.suffix in {".yml", ".yaml"}:
            text = read_text(p)
            if text:
                for m in re.finditer(rf"^\s+{NAME}\s*:", text, re.M):
                    _add(c.ci_set, m.group(1), rel)
        elif re.match(r"(docker-)?compose.*\.ya?ml$", name) or name in ("compose.yml", "compose.yaml"):
            text = read_text(p)
            if text:
                for m in re.finditer(rf"^\s+(?:-\s*)?{NAME}\s*[:=]", text, re.M):
                    _add(c.compose_set, m.group(1), rel)
        elif name.lower() == "readme.md":
            text = read_text(p)
            if text:
                for m in re.finditer(rf"`{NAME}`", text):
                    _add(c.readme, m.group(1), rel)
    return c


def analyze(c: Census, cfg: dict) -> dict:
    ign = cfg["ignore_vars"]
    reads = {k: v for k, v in c.reads.items() if not is_ignored(k, ign)}
    documented = {k for k in c.documented if not is_ignored(k, ign)}
    declared = documented | set(c.readme) | set(c.compose_set)
    return {
        "undocumented": {k: reads[k] for k in sorted(reads) if k not in documented and k not in c.readme},
        "unused": {k: c.documented[k] for k in sorted(documented) if k not in c.reads},
        "not_in_ci": sorted(k for k in reads if k in documented and c.ci_set and k not in c.ci_set),
        "total_reads": len(reads),
        "total_documented": len(documented),
        "declared": sorted(declared),
    }
