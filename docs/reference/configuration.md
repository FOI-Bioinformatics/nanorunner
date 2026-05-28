# Configuration reference

The CLI builds two frozen dataclasses, `ReplayConfig` and
`GenerateConfig`, defined in `nanopore_simulator/config.py`. Both
validate their fields in `__post_init__`. This page summarises every
field.

## ReplayConfig

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `source_dir` | `Path` | required | Directory of FASTQ files or a single FASTQ file. |
| `target_dir` | `Path` | required | Output directory. |
| `operation` | `str` | `"copy"` | `"copy"` or `"link"`. |
| `interval` | `float` | `5.0` | Base seconds between batches. |
| `batch_size` | `int` | `1` | Files per batch. |
| `file_extensions` | `tuple[str, ...]` | `(".fastq", ".fq", ".fastq.gz", ".fq.gz")` | Recognised FASTQ extensions. |
| `timing_model` | `str` | `"uniform"` | `uniform`, `random`, `poisson`, or `adaptive`. |
| `timing_params` | `dict` | `{}` | Model-specific parameters. |
| `parallel` | `bool` | `False` | Enable thread-pool execution. |
| `workers` | `int` | `4` | Worker thread count. |
| `monitor_type` | `str` | `"basic"` | `basic`, `enhanced`, or `none`. |
| `adapter` | `Optional[str]` | `None` | Pipeline adapter for validation. |
| `reads_per_output` | `Optional[int]` | `None` | Rechunk into N-read pieces. |
| `structure` | `str` | `"auto"` | Input layout override: `auto`, `singleplex`, `multiplex`. |
| `output_structure` | `str` | `"preserve"` | Target layout: `preserve`, `flat`, `barcoded`. |
| `output_barcodes` | `int` | `1` | Barcode dir count when `output_structure="barcoded"`. |
| `output_barcode_pattern` | `str` | `"barcode{:02d}"` | Format string for barcode dir names. |
| `output_file_prefix` | `Optional[str]` | `None` | Override chunk filename stem. |

### Validation rules

- `interval >= 0`, `batch_size >= 1`, `workers >= 1`.
- `operation in {"copy", "link"}`.
- `reads_per_output >= 1` and incompatible with `operation == "link"`.
- `output_structure != "preserve"` requires `reads_per_output` set and
  `operation == "copy"`.
- `output_barcodes >= 1`.
- `output_barcode_pattern` must accept one positional integer
  (`"barcode{:02d}"`, `"bc{}"`, ...).

## GenerateConfig

| Field | Type | Default | Purpose |
| --- | --- | --- | --- |
| `target_dir` | `Path` | required | Output directory. |
| `genome_inputs` | `Optional[List[Path]]` | `None` | FASTA paths. |
| `species_inputs` | `Optional[List[str]]` | `None` | Species names. |
| `mock_name` | `Optional[str]` | `None` | Mock community ID. |
| `taxid_inputs` | `Optional[List[str]]` | `None` | NCBI taxids. |
| `accession_inputs` | `Optional[List[str]]` | `None` | Explicit NCBI assembly accessions (`GCA_/GCF_NNNNNNNNN.V`). |
| `abundances` | `Optional[List[float]]` | `None` | Per-genome abundances (sum to 1.0). |
| `read_count` | `int` | `1000` | Total reads across all genomes. |
| `interval` | `float` | `5.0` | Base seconds between batches. |
| `batch_size` | `int` | `100` | Files per batch. |
| `generator_backend` | `str` | `"auto"` | `auto`, `builtin`, `badread`, `nanosim`. |
| `mean_length` | `int` | `5000` | Mean read length in bases. |
| `std_length` | `int` | `2000` | Read length standard deviation. |
| `min_length` | `int` | `200` | Minimum read length. |
| `mean_quality` | `float` | `20.0` | Mean Phred quality. |
| `std_quality` | `float` | `4.0` | Quality standard deviation. |
| `reads_per_file` | `int` | `100` | Reads per output file. |
| `output_format` | `str` | `"fastq.gz"` | `fastq` or `fastq.gz`. |
| `mix_reads` | `bool` | `False` | Mix reads across genomes (singleplex only). |
| `timing_model` | `str` | `"uniform"` | Timing model name. |
| `timing_params` | `dict` | `{}` | Model-specific parameters. |
| `parallel` | `bool` | `False` | Enable thread-pool execution. |
| `workers` | `int` | `4` | Worker thread count. |
| `monitor_type` | `str` | `"basic"` | `basic`, `enhanced`, or `none`. |
| `adapter` | `Optional[str]` | `None` | Pipeline adapter for validation. |
| `structure` | `str` | `"singleplex"` | Output layout: `singleplex` or `multiplex`. |
| `offline_mode` | `bool` | `False` | Use only cached genomes. |

### Validation rules

- At least one of `genome_inputs`, `species_inputs`, `mock_name`,
  `taxid_inputs`, or `accession_inputs` must be provided.
- `read_count >= 1`.
- `output_format in {"fastq", "fastq.gz"}`.
- `structure in {"singleplex", "multiplex"}`.
- If `abundances` is provided it must match the number of
  `genome_inputs` and sum to 1.0 (+/- 0.01).
