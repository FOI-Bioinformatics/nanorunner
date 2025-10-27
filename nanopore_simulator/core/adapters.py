"""Pipeline adapter interface for supporting multiple sequencing pipelines"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any, Optional
import re
from dataclasses import dataclass


@dataclass
class PipelineRequirements:
    """Requirements for a pipeline adapter"""

    name: str
    description: str
    expected_patterns: List[str]  # File patterns the pipeline expects
    required_structure: Optional[str] = (
        None  # "singleplex", "multiplex", or None for flexible
    )
    barcode_patterns: Optional[List[str]] = None  # Custom barcode patterns
    metadata_files: Optional[List[str]] = None  # Required metadata files
    validation_rules: Optional[Dict[str, Any]] = None  # Custom validation rules


class PipelineAdapter(ABC):
    """Abstract base class for pipeline adapters"""

    def __init__(self, requirements: PipelineRequirements):
        self.requirements = requirements

        # Convert glob patterns to regex patterns for file matching
        self._compiled_patterns = []
        for pattern in requirements.expected_patterns:
            # Convert glob pattern to regex
            regex_pattern = self._glob_to_regex(pattern)
            self._compiled_patterns.append(re.compile(regex_pattern))

        if requirements.barcode_patterns:
            self._barcode_patterns = [
                re.compile(pattern) for pattern in requirements.barcode_patterns
            ]
        else:
            # Default barcode patterns
            self._barcode_patterns = [
                re.compile(r"^barcode\d+$"),
                re.compile(r"^BC\d+$"),
                re.compile(r"^bc\d+$"),
                re.compile(r"^unclassified$"),
            ]

    @abstractmethod
    def validate_structure(self, target_dir: Path) -> bool:
        """Validate that the target directory structure meets pipeline requirements"""
        pass

    @abstractmethod
    def get_expected_patterns(self) -> List[str]:
        """Get file patterns expected by this pipeline"""
        pass

    def _glob_to_regex(self, glob_pattern: str) -> str:
        """Convert a glob pattern to a regex pattern"""
        # Handle ** for recursive directory matching
        if glob_pattern.startswith("**/"):
            # **/*.ext matches any file with .ext in any subdirectory
            file_pattern = glob_pattern[3:]  # Remove "**/"
            # Convert to regex that matches the file pattern at end of path
            regex_pattern = r".*" + re.escape(file_pattern).replace(
                r"\*", ".*"
            ).replace(r"\?", ".")
        else:
            # Simple glob pattern
            regex_pattern = (
                re.escape(glob_pattern).replace(r"\*", ".*").replace(r"\?", ".")
            )

        return regex_pattern + "$"  # Ensure full match

    def supports_file(self, file_path: Path) -> bool:
        """Check if a file is supported by this pipeline"""
        filename = file_path.name.lower()
        return any(pattern.search(filename) for pattern in self._compiled_patterns)

    def is_barcode_directory(self, dir_path: Path) -> bool:
        """Check if a directory matches barcode patterns"""
        dir_name = dir_path.name.lower()
        return any(pattern.match(dir_name) for pattern in self._barcode_patterns)

    def get_validation_report(self, target_dir: Path) -> Dict[str, Any]:
        """Get detailed validation report"""
        report: Dict[str, Any] = {
            "pipeline": self.requirements.name,
            "valid": False,
            "structure_valid": False,
            "files_found": [],
            "missing_files": [],
            "warnings": [],
            "errors": [],
        }

        try:
            # Check structure
            report["structure_valid"] = self.validate_structure(target_dir)

            # Check for expected files
            found_files = []
            for pattern_str in self.requirements.expected_patterns:
                pattern_files = list(target_dir.glob(pattern_str))
                found_files.extend(pattern_files)

            report["files_found"] = [
                str(f.relative_to(target_dir)) for f in found_files
            ]

            # Check for required metadata files
            if self.requirements.metadata_files:
                for metadata_file in self.requirements.metadata_files:
                    metadata_path = target_dir / metadata_file
                    if not metadata_path.exists():
                        report["missing_files"].append(metadata_file)
                        report["warnings"].append(
                            f"Missing metadata file: {metadata_file}"
                        )

            # Overall validation
            report["valid"] = (
                report["structure_valid"]
                and len(report["files_found"]) > 0
                and len(report["missing_files"]) == 0
            )

        except Exception as e:
            report["errors"].append(f"Validation error: {str(e)}")

        return report


class NanometanfAdapter(PipelineAdapter):
    """Adapter for the nanometanf pipeline"""

    def __init__(self) -> None:
        requirements = PipelineRequirements(
            name="nanometanf",
            description="Oxford Nanopore taxonomic analysis pipeline",
            expected_patterns=[
                "**/*.fastq",
                "**/*.fq",
                "**/*.fastq.gz",
                "**/*.fq.gz",
                "**/*.pod5",
            ],
            required_structure=None,  # Supports both singleplex and multiplex
            barcode_patterns=[
                r"^barcode\d+$",
                r"^BC\d+$",
                r"^bc\d+$",
                r"^unclassified$",
            ],
            metadata_files=None,  # No specific metadata required
            validation_rules={
                "min_files": 1,
                "supported_extensions": [
                    ".fastq",
                    ".fq",
                    ".fastq.gz",
                    ".fq.gz",
                    ".pod5",
                ],
            },
        )
        super().__init__(requirements)

    def validate_structure(self, target_dir: Path) -> bool:
        """Validate nanometanf directory structure"""
        if not target_dir.exists():
            return False

        # Check for any supported files
        supported_files = []
        for pattern_str in self.requirements.expected_patterns:
            pattern_files = list(target_dir.glob(pattern_str))
            supported_files.extend(pattern_files)

        # Must have at least one supported file
        min_files = 1
        if self.requirements.validation_rules is not None:
            min_files = self.requirements.validation_rules.get("min_files", 1)
        if len(supported_files) < min_files:
            return False

        # Check if structure is consistent (either all in root or all in barcode dirs)
        root_files = [f for f in supported_files if f.parent == target_dir]
        barcode_files = [f for f in supported_files if f.parent != target_dir]

        if root_files and barcode_files:
            # Mixed structure - check if barcode directories are valid
            barcode_dirs = set(f.parent for f in barcode_files)
            for barcode_dir in barcode_dirs:
                if not self.is_barcode_directory(barcode_dir):
                    return False

        return True

    def get_expected_patterns(self) -> List[str]:
        """Get file patterns expected by nanometanf"""
        return self.requirements.expected_patterns.copy()


class GenericAdapter(PipelineAdapter):
    """Generic adapter for custom pipeline configurations"""

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize with custom configuration

        Config format:
        {
            'name': 'pipeline_name',
            'description': 'Pipeline description',
            'patterns': ['*.fastq', '*.fq'],
            'structure': 'singleplex|multiplex|flexible',
            'barcode_patterns': ['custom_pattern'],
            'metadata_files': ['sample_sheet.csv'],
            'min_files': 1
        }
        """
        requirements = PipelineRequirements(
            name=config.get("name", "generic"),
            description=config.get("description", "Generic pipeline adapter"),
            expected_patterns=config.get("patterns", ["**/*.fastq", "**/*.fq"]),
            required_structure=config.get("structure"),
            barcode_patterns=config.get("barcode_patterns"),
            metadata_files=config.get("metadata_files"),
            validation_rules={
                "min_files": config.get("min_files", 1),
                "strict_structure": config.get("strict_structure", False),
            },
        )
        super().__init__(requirements)

    def validate_structure(self, target_dir: Path) -> bool:
        """Validate generic pipeline structure"""
        if not target_dir.exists():
            return False

        # Check for supported files using filesystem glob
        supported_files = []
        for pattern_str in self.requirements.expected_patterns:
            # Handle different pattern types
            if pattern_str.startswith("**/"):
                # Recursive pattern
                pattern_files = list(target_dir.rglob(pattern_str[3:]))
            else:
                # Simple pattern in root or direct glob
                pattern_files = list(target_dir.glob(pattern_str))
                # Also check subdirectories for multiplex structures
                for subdir in target_dir.iterdir():
                    if subdir.is_dir():
                        pattern_files.extend(subdir.glob(pattern_str))

            supported_files.extend(pattern_files)

        min_files = 1
        if self.requirements.validation_rules is not None:
            min_files = self.requirements.validation_rules.get("min_files", 1)
        if len(supported_files) < min_files:
            return False

        # Check structure requirements
        if self.requirements.required_structure:
            if self.requirements.required_structure == "singleplex":
                # All files should be in root directory
                root_files = [f for f in supported_files if f.parent == target_dir]
                return len(root_files) == len(supported_files)

            elif self.requirements.required_structure == "multiplex":
                # All files should be in barcode subdirectories
                barcode_files = [f for f in supported_files if f.parent != target_dir]
                if len(barcode_files) != len(supported_files):
                    return False

                # Validate barcode directory names
                barcode_dirs = set(f.parent for f in barcode_files)
                return all(self.is_barcode_directory(bd) for bd in barcode_dirs)

        return True

    def get_expected_patterns(self) -> List[str]:
        """Get file patterns expected by this generic pipeline"""
        return self.requirements.expected_patterns.copy()


class KrackenAdapter(PipelineAdapter):
    """Adapter for Kraken2/KrakenUniq pipelines"""

    def __init__(self) -> None:
        requirements = PipelineRequirements(
            name="kraken",
            description="Kraken2/KrakenUniq taxonomic classification pipeline",
            expected_patterns=["**/*.fastq", "**/*.fq", "**/*.fastq.gz", "**/*.fq.gz"],
            required_structure=None,
            metadata_files=None,
            validation_rules={
                "min_files": 1,
                "supported_extensions": [".fastq", ".fq", ".fastq.gz", ".fq.gz"],
            },
        )
        super().__init__(requirements)

    def validate_structure(self, target_dir: Path) -> bool:
        """Validate Kraken pipeline structure"""
        if not target_dir.exists():
            return False

        # Check for supported files
        supported_files = []
        for pattern_str in self.requirements.expected_patterns:
            pattern_files = list(target_dir.glob(pattern_str))
            supported_files.extend(pattern_files)

        return len(supported_files) >= 1

    def get_expected_patterns(self) -> List[str]:
        """Get file patterns expected by Kraken"""
        return self.requirements.expected_patterns.copy()


class MiniknifeAdapter(PipelineAdapter):
    """Adapter for Miniknife pipeline"""

    def __init__(self) -> None:
        requirements = PipelineRequirements(
            name="miniknife",
            description="Miniknife nanopore taxonomic analysis pipeline",
            expected_patterns=["**/*.fastq", "**/*.fq", "**/*.fastq.gz", "**/*.fq.gz"],
            required_structure="multiplex",  # Typically requires barcoded samples
            barcode_patterns=[
                r"^barcode\d+$",
                r"^bc\d+$",  # Changed to lowercase since is_barcode_directory uses .lower()
                r"^sample\d+$",
            ],
            metadata_files=["sample_sheet.tsv"],
            validation_rules={"min_files": 1, "require_sample_sheet": True},
        )
        super().__init__(requirements)

    def validate_structure(self, target_dir: Path) -> bool:
        """Validate Miniknife pipeline structure"""
        if not target_dir.exists():
            return False

        # Check for sample sheet if required
        require_sample_sheet = False
        if self.requirements.validation_rules is not None:
            require_sample_sheet = self.requirements.validation_rules.get(
                "require_sample_sheet", False
            )
        if require_sample_sheet:
            sample_sheet = target_dir / "sample_sheet.tsv"
            if not sample_sheet.exists():
                return False

        # Check for barcode structure
        barcode_dirs = [
            d
            for d in target_dir.iterdir()
            if d.is_dir() and self.is_barcode_directory(d)
        ]

        if not barcode_dirs:
            return False

        # Check for files in barcode directories
        total_files = 0
        for barcode_dir in barcode_dirs:
            for pattern_str in self.requirements.expected_patterns:
                # Remove ** prefix for individual directory search
                simple_pattern = pattern_str.replace("**/", "")
                files = list(barcode_dir.glob(simple_pattern))
                total_files += len(files)

        return total_files >= 1

    def get_expected_patterns(self) -> List[str]:
        """Get file patterns expected by Miniknife"""
        return self.requirements.expected_patterns.copy()


class AdapterManager:
    """Manages pipeline adapters"""

    def __init__(self) -> None:
        self.adapters = {
            "nanometanf": NanometanfAdapter(),
            "kraken": KrackenAdapter(),
            "miniknife": MiniknifeAdapter(),
        }

    def get_adapter(self, name: str) -> Optional[PipelineAdapter]:
        """Get a pipeline adapter by name"""
        adapter = self.adapters.get(name.lower())
        return adapter if adapter is not None else None

    def add_adapter(self, name: str, adapter: PipelineAdapter) -> None:
        """Add a custom adapter"""
        self.adapters[name.lower()] = adapter

    def list_adapters(self) -> Dict[str, str]:
        """List all available adapters with descriptions"""
        return {
            name: adapter.requirements.description
            for name, adapter in self.adapters.items()
        }

    def validate_for_pipeline(
        self, pipeline_name: str, target_dir: Path
    ) -> Dict[str, Any]:
        """Validate directory structure for a specific pipeline"""
        adapter = self.get_adapter(pipeline_name)
        if not adapter:
            return {"valid": False, "error": f"Unknown pipeline: {pipeline_name}"}

        return adapter.get_validation_report(target_dir)

    def get_compatible_pipelines(self, target_dir: Path) -> List[str]:
        """Get list of pipelines compatible with the target directory"""
        compatible = []

        for name, adapter in self.adapters.items():
            try:
                if adapter.validate_structure(target_dir):
                    compatible.append(name)
            except Exception:
                # Skip adapters that fail validation
                continue

        return compatible

    def create_generic_adapter(self, config: Dict[str, Any]) -> GenericAdapter:
        """Create a generic adapter with custom configuration"""
        return GenericAdapter(config)


# Global adapter manager instance
adapter_manager = AdapterManager()


def get_available_adapters() -> Dict[str, str]:
    """Get all available pipeline adapters"""
    return adapter_manager.list_adapters()


def validate_for_pipeline(pipeline_name: str, target_dir: Path) -> Dict[str, Any]:
    """Validate directory for a specific pipeline"""
    return adapter_manager.validate_for_pipeline(pipeline_name, target_dir)


def get_compatible_pipelines(target_dir: Path) -> List[str]:
    """Get pipelines compatible with target directory"""
    return adapter_manager.get_compatible_pipelines(target_dir)


def get_pipeline_adapter(name: str) -> Optional[PipelineAdapter]:
    """Get a pipeline adapter by name"""
    return adapter_manager.get_adapter(name)
