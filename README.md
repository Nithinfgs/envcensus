# envcensus

Which environment variables does your code actually read, and which does anyone tell the next person to set?

`envcensus` scans a project, lists every env var the source reads, and compares that with what `.env.example`, the README, docker-compose and your GitHub workflows declare. Offline, standard library only, no config required.

```
$ envcensus .
12 variables read in code, 9 documented in .env.example

UNDOCUMENTED (read by code, absent from .env.example/README):
  STRIPE_WEBHOOK_SECRET  src/billing.py:41 (+1 more)
  FEATURE_X_ENABLED  web/flags.ts:7

UNUSED (documented, but no code reads it):
  OLD_REDIS_URL  in .env.example

NOT SET IN CI (documented and read, but no workflow sets it):
  DATABASE_URL
```

## Install

```bash
pip install git+https://github.com/Nithinfgs/envcensus.git
```

Requires Python 3.9+. No dependencies.

## Usage

```bash
envcensus                      # scan the current directory
envcensus path/to/project
envcensus --json               # machine-readable report
envcensus --fail-on any        # exit 1 on undocumented OR unused variables
```

Exit codes: `0` clean, `1` drift found (per `--fail-on`, default `undocumented`), `2` bad input or config. Use it as a CI step to stop undocumented variables from landing.

## What it recognises

| Language | Patterns |
|---|---|
| Python | `os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")` |
| JS / TS | `process.env.X`, `process.env["X"]`, `import.meta.env.X`, `Deno.env.get("X")` |
| Go | `os.Getenv("X")`, `os.LookupEnv("X")` |
| Rust | `env::var("X")`, `std::env::var_os("X")` |
| Ruby | `ENV["X"]`, `ENV.fetch("X")` |
| Java | `System.getenv("X")` |
| PHP | `getenv("X")` |
| Shell | `$X`, `${X:-default}` (variables the script assigns itself are skipped) |

Declarations come from `.env.example` / `.env.sample` / `.env.template` (commented-out `# X=` lines count), backticked names in `README.md`, and `docker-compose` files. Workflow `env:` keys in `.github/workflows/` feed the CI check.

Only `UPPER_CASE` literal names are tracked. Dynamically built names (`os.getenv(name)`) can't be known statically and are skipped.

## Configuration

Optional `envcensus.json` in the project root (or `--config path`). See [envcensus.example.json](envcensus.example.json).

| Key | Meaning |
|---|---|
| `ignore_vars` | Names or `fnmatch` globs never reported (defaults include `HOME`, `PATH`, `CI`, `GITHUB_*`, `NODE_ENV`) |
| `exclude_dirs` | Directory names skipped (defaults include `node_modules`, `.git`, `dist`, `.venv`) |

Setting a key replaces its default list.

## Limitations

- Pattern-based, not a full parser: a commented-out read still counts, and reads through wrapper helpers (`config.get("X")`) are not seen.
- The CI check only runs when at least one workflow declares env keys.
- Files over 2 MB or not valid UTF-8 are skipped.

## Development

```bash
python -m unittest discover -s tests -v
```

## License

MIT
