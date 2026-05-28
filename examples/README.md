# NanoRunner examples

Six runnable scripts that walk from a one-minute replay smoke test through
a real-genome generate workflow. Each script is self-contained, creates
its own temporary output directory, and cleans up after itself.

All scripts target the **v3.1.0 API**.

## At a glance

| # | Script | Level | Time | What it covers |
|---|---|---|---|---|
| 01 | `01_basic_simulation.py` | beginner | ~1 min | minimal `ReplayConfig` + `run_replay` against a singleplex source |
| 02 | `02_timing_models.py` | intermediate | ~3 min | all four timing models (uniform / random / poisson / adaptive) against the same data |
| 03 | `03_parallel_processing.py` | intermediate | ~2 min | sequential vs parallel batches with optional resource monitoring |
| 04 | `04_configuration_profiles.py` | intermediate | ~2 min | applying and overriding built-in profiles |
| 05 | `05_pipeline_integration.py` | advanced | ~3 min | post-run validation against pipeline adapters (`nanometa`, `kraken`) |
| 06 | `06_practical_genome_test.py` | advanced | ~5 min | generate mode end-to-end with real NCBI genomes |

The examples are designed to be read in order; each builds on a concept
introduced earlier.

## Running an example

```bash
pip install -e .                                # one-time setup
python examples/01_basic_simulation.py          # run from the repo root
```

Examples 01-05 use the bundled fixtures under `examples/sample_data/`:

```
sample_data/
├── singleplex/
│   ├── sample1.fastq
│   └── sample2.fastq
└── multiplex/
    ├── barcode01/
    │   └── reads.fastq
    └── barcode02/
        └── reads.fastq
```

Example 06 downloads three small reference genomes (Lambda phage, *S.
aureus*, *E. coli*) via the NCBI `datasets` CLI on first run and reuses
the local cache afterwards.

## Public API the examples use

```python
# Top-level entry points
from nanopore_simulator import (
    ReplayConfig, GenerateConfig,
    run_replay, run_generate,
)

# Configuration profiles
from nanopore_simulator.profiles import (
    PROFILES, get_profile, apply_profile, list_profiles,
)

# Pipeline adapters
from nanopore_simulator.adapters import (
    ADAPTERS, validate_output, list_adapters,
)

# Mock communities
from nanopore_simulator.mocks import BUILTIN_MOCKS, get_mock

# Backends, timing models, dependency probing -- usually not needed
# directly; ReplayConfig / GenerateConfig wire them up internally.
from nanopore_simulator.generators import (
    create_generator, detect_available_backends,
)
from nanopore_simulator.timing import create_timing_model
from nanopore_simulator.deps import check_all_dependencies
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ImportError: No module named nanopore_simulator` | `pip install -e .` from the repo root |
| Sample data not found | run examples from the repo root, not from inside `examples/` |
| `datasets: command not found` (example 06) | `conda install -c conda-forge ncbi-datasets-cli` |
| No enhanced monitor metrics | `pip install nanorunner[enhanced]` (adds `psutil`) |

To wipe the genome cache that example 06 populates:

```bash
rm -rf ~/.cache/nanorunner_genomes/
```

## Where to go next

Once the examples make sense, the [documentation index](../docs/README.md)
has a guided introduction, the full CLI reference, and pipeline
integration notes.
