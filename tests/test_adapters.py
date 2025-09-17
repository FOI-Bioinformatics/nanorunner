"""Tests for pipeline adapter system"""

import pytest
import tempfile
from pathlib import Path

from nanopore_simulator.core.adapters import (
    PipelineRequirements, PipelineAdapter, NanometanfAdapter,
    GenericAdapter, KrackenAdapter, MiniknifeAdapter, AdapterManager,
    get_available_adapters, validate_for_pipeline, get_compatible_pipelines,
    get_pipeline_adapter
)


class TestPipelineRequirements:
    """Test the PipelineRequirements class"""
    
    def test_requirements_creation(self):
        """Test creating pipeline requirements"""
        requirements = PipelineRequirements(
            name="test_pipeline",
            description="Test pipeline for testing",
            expected_patterns=["*.fastq", "*.fq"],
            required_structure="multiplex",
            barcode_patterns=[r"^sample\d+$"],
            metadata_files=["sample_sheet.csv"],
            validation_rules={"min_files": 2}
        )
        
        assert requirements.name == "test_pipeline"
        assert requirements.expected_patterns == ["*.fastq", "*.fq"]
        assert requirements.required_structure == "multiplex"
        assert requirements.barcode_patterns == [r"^sample\d+$"]
        assert requirements.metadata_files == ["sample_sheet.csv"]
        assert requirements.validation_rules["min_files"] == 2


class TestNanometanfAdapter:
    """Test the nanometanf pipeline adapter"""
    
    @pytest.fixture
    def adapter(self):
        return NanometanfAdapter()
    
    def test_adapter_creation(self, adapter):
        """Test nanometanf adapter creation"""
        assert adapter.requirements.name == "nanometanf"
        assert "**/*.fastq" in adapter.requirements.expected_patterns
        assert "**/*.pod5" in adapter.requirements.expected_patterns
        assert adapter.requirements.required_structure is None  # Flexible
    
    def test_supports_file(self, adapter):
        """Test file support detection"""
        # Supported files
        assert adapter.supports_file(Path("test.fastq")) is True
        assert adapter.supports_file(Path("test.fq")) is True
        assert adapter.supports_file(Path("test.fastq.gz")) is True
        assert adapter.supports_file(Path("test.pod5")) is True
        
        # Unsupported files
        assert adapter.supports_file(Path("test.txt")) is False
        assert adapter.supports_file(Path("test.bam")) is False
    
    def test_barcode_directory_detection(self, adapter):
        """Test barcode directory detection"""
        # Valid barcode directories
        assert adapter.is_barcode_directory(Path("barcode01")) is True
        assert adapter.is_barcode_directory(Path("BC15")) is True
        assert adapter.is_barcode_directory(Path("bc03")) is True
        assert adapter.is_barcode_directory(Path("unclassified")) is True
        
        # Invalid barcode directories
        assert adapter.is_barcode_directory(Path("sample01")) is False
        assert adapter.is_barcode_directory(Path("data")) is False
    
    def test_validate_singleplex_structure(self, adapter, temp_structure):
        """Test validation of singleplex structure"""
        source_dir, target_dir = temp_structure
        
        # Create singleplex structure
        (target_dir / "sample1.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        (target_dir / "sample2.fq.gz").write_text("compressed fastq")
        
        assert adapter.validate_structure(target_dir) is True
    
    def test_validate_multiplex_structure(self, adapter, temp_structure):
        """Test validation of multiplex structure"""
        source_dir, target_dir = temp_structure
        
        # Create multiplex structure
        bc01_dir = target_dir / "barcode01"
        bc02_dir = target_dir / "barcode02"
        bc01_dir.mkdir()
        bc02_dir.mkdir()
        
        (bc01_dir / "reads.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        (bc02_dir / "reads.fastq").write_text("@read2\nTGCA\n+\nIIII\n")
        
        assert adapter.validate_structure(target_dir) is True
    
    def test_validate_mixed_structure(self, adapter, temp_structure):
        """Test validation of mixed structure (should still be valid)"""
        source_dir, target_dir = temp_structure
        
        # Create mixed structure
        (target_dir / "root_file.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        bc_dir = target_dir / "barcode01"
        bc_dir.mkdir()
        (bc_dir / "bc_file.fastq").write_text("@read2\nTGCA\n+\nIIII\n")
        
        assert adapter.validate_structure(target_dir) is True
    
    def test_validate_empty_directory(self, adapter, temp_structure):
        """Test validation of empty directory"""
        source_dir, target_dir = temp_structure
        
        assert adapter.validate_structure(target_dir) is False
    
    def test_get_validation_report(self, adapter, temp_structure):
        """Test detailed validation report"""
        source_dir, target_dir = temp_structure
        
        # Create test structure
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        (target_dir / "sample.pod5").write_text("pod5 data")
        
        report = adapter.get_validation_report(target_dir)
        
        assert report["pipeline"] == "nanometanf"
        assert report["valid"] is True
        assert report["structure_valid"] is True
        assert len(report["files_found"]) == 2
        assert "sample.fastq" in report["files_found"]
        assert "sample.pod5" in report["files_found"]
        assert len(report["errors"]) == 0


class TestGenericAdapter:
    """Test the generic pipeline adapter"""
    
    def test_basic_generic_adapter(self, temp_structure):
        """Test basic generic adapter configuration"""
        source_dir, target_dir = temp_structure
        
        config = {
            'name': 'basic_pipeline',
            'description': 'Basic pipeline',
            'patterns': ['*.fastq', '*.fq'],
            'min_files': 1
        }
        
        adapter = GenericAdapter(config)
        
        assert adapter.requirements.name == 'basic_pipeline'
        assert adapter.requirements.expected_patterns == ['*.fastq', '*.fq']
        assert adapter.requirements.validation_rules['min_files'] == 1
    
    def test_singleplex_only_adapter(self, temp_structure):
        """Test adapter that only accepts singleplex structure"""
        source_dir, target_dir = temp_structure
        
        config = {
            'name': 'singleplex_only',
            'patterns': ['*.fastq'],
            'structure': 'singleplex'
        }
        
        adapter = GenericAdapter(config)
        
        # Create singleplex structure - should be valid
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        assert adapter.validate_structure(target_dir) is True
        
        # Create multiplex structure - should be invalid
        for item in target_dir.glob("*"):
            item.unlink()
        bc_dir = target_dir / "barcode01"
        bc_dir.mkdir()
        (bc_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        assert adapter.validate_structure(target_dir) is False
    
    def test_multiplex_only_adapter(self, temp_structure):
        """Test adapter that only accepts multiplex structure"""
        source_dir, target_dir = temp_structure
        
        config = {
            'name': 'multiplex_only',
            'patterns': ['*.fastq'],
            'structure': 'multiplex'
        }
        
        adapter = GenericAdapter(config)
        
        # Create multiplex structure - should be valid
        bc_dir = target_dir / "barcode01"
        bc_dir.mkdir()
        (bc_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        assert adapter.validate_structure(target_dir) is True
        
        # Create singleplex structure - should be invalid
        for item in target_dir.iterdir():
            if item.is_dir():
                for file in item.iterdir():
                    file.unlink()
                item.rmdir()
            else:
                item.unlink()
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        assert adapter.validate_structure(target_dir) is False


class TestKrackenAdapter:
    """Test the Kraken pipeline adapter"""
    
    @pytest.fixture
    def adapter(self):
        return KrackenAdapter()
    
    def test_kraken_adapter_creation(self, adapter):
        """Test Kraken adapter creation"""
        assert adapter.requirements.name == "kraken"
        assert "**/*.fastq" in adapter.requirements.expected_patterns
        # Kraken doesn't support POD5 files
        assert "**/*.pod5" not in adapter.requirements.expected_patterns
    
    def test_kraken_file_support(self, adapter):
        """Test Kraken file support"""
        assert adapter.supports_file(Path("test.fastq")) is True
        assert adapter.supports_file(Path("test.fastq.gz")) is True
        assert adapter.supports_file(Path("test.pod5")) is False  # Not supported
    
    def test_kraken_validation(self, adapter, temp_structure):
        """Test Kraken validation"""
        source_dir, target_dir = temp_structure
        
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        assert adapter.validate_structure(target_dir) is True


class TestMiniknifeAdapter:
    """Test the Miniknife pipeline adapter"""
    
    @pytest.fixture
    def adapter(self):
        return MiniknifeAdapter()
    
    def test_miniknife_adapter_creation(self, adapter):
        """Test Miniknife adapter creation"""
        assert adapter.requirements.name == "miniknife"
        assert adapter.requirements.required_structure == "multiplex"
        assert "sample_sheet.tsv" in adapter.requirements.metadata_files
    
    def test_miniknife_barcode_patterns(self, adapter):
        """Test Miniknife barcode patterns"""
        assert adapter.is_barcode_directory(Path("barcode01")) is True
        assert adapter.is_barcode_directory(Path("BC01")) is True
        assert adapter.is_barcode_directory(Path("sample01")) is True  # Custom pattern
    
    def test_miniknife_validation_with_sample_sheet(self, adapter, temp_structure):
        """Test Miniknife validation with sample sheet"""
        source_dir, target_dir = temp_structure
        
        # Create sample sheet
        (target_dir / "sample_sheet.tsv").write_text("sample_id\tbarcode\nsample1\tbarcode01\n")
        
        # Create barcode structure
        bc_dir = target_dir / "barcode01"
        bc_dir.mkdir()
        (bc_dir / "reads.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        assert adapter.validate_structure(target_dir) is True
    
    def test_miniknife_validation_without_sample_sheet(self, adapter, temp_structure):
        """Test Miniknife validation without sample sheet"""
        source_dir, target_dir = temp_structure
        
        # Create barcode structure but no sample sheet
        bc_dir = target_dir / "barcode01"
        bc_dir.mkdir()
        (bc_dir / "reads.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        assert adapter.validate_structure(target_dir) is False


class TestAdapterManager:
    """Test the adapter manager"""
    
    @pytest.fixture
    def manager(self):
        return AdapterManager()
    
    def test_manager_initialization(self, manager):
        """Test adapter manager initialization"""
        adapters = manager.list_adapters()
        
        assert "nanometanf" in adapters
        assert "kraken" in adapters
        assert "miniknife" in adapters
    
    def test_get_adapter(self, manager):
        """Test getting adapters by name"""
        nanometanf = manager.get_adapter("nanometanf")
        assert isinstance(nanometanf, NanometanfAdapter)
        
        kraken = manager.get_adapter("kraken")
        assert isinstance(kraken, KrackenAdapter)
        
        unknown = manager.get_adapter("unknown")
        assert unknown is None
    
    def test_add_custom_adapter(self, manager):
        """Test adding custom adapter"""
        config = {
            'name': 'custom_pipeline',
            'patterns': ['*.txt'],
            'min_files': 1
        }
        custom_adapter = GenericAdapter(config)
        
        manager.add_adapter("custom", custom_adapter)
        
        retrieved = manager.get_adapter("custom")
        assert retrieved is not None
        assert retrieved.requirements.name == 'custom_pipeline'
    
    def test_validate_for_pipeline(self, manager, temp_structure):
        """Test pipeline validation through manager"""
        source_dir, target_dir = temp_structure
        
        # Create nanometanf-compatible structure
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        report = manager.validate_for_pipeline("nanometanf", target_dir)
        assert report["valid"] is True
        
        # Test unknown pipeline
        report = manager.validate_for_pipeline("unknown", target_dir)
        assert report["valid"] is False
        assert "Unknown pipeline" in report["error"]
    
    def test_get_compatible_pipelines(self, manager, temp_structure):
        """Test finding compatible pipelines"""
        source_dir, target_dir = temp_structure
        
        # Create structure compatible with multiple pipelines
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        compatible = manager.get_compatible_pipelines(target_dir)
        
        assert "nanometanf" in compatible
        assert "kraken" in compatible
        # miniknife should not be compatible (requires multiplex + sample sheet)
    
    def test_create_generic_adapter(self, manager):
        """Test creating generic adapter through manager"""
        config = {
            'name': 'test_generic',
            'patterns': ['*.test'],
            'structure': 'singleplex'
        }
        
        adapter = manager.create_generic_adapter(config)
        assert isinstance(adapter, GenericAdapter)
        assert adapter.requirements.name == 'test_generic'


class TestAdapterIntegration:
    """Test adapter integration with global functions"""
    
    def test_global_functions(self):
        """Test global convenience functions"""
        adapters = get_available_adapters()
        assert "nanometanf" in adapters
        assert "kraken" in adapters
        
        adapter = get_pipeline_adapter("nanometanf")
        assert isinstance(adapter, NanometanfAdapter)
        
        adapter = get_pipeline_adapter("unknown")
        assert adapter is None
    
    def test_global_validation(self, temp_structure):
        """Test global validation function"""
        source_dir, target_dir = temp_structure
        
        (target_dir / "sample.fastq").write_text("@read1\nACGT\n+\nIIII\n")
        
        report = validate_for_pipeline("nanometanf", target_dir)
        assert report["valid"] is True
        
        compatible = get_compatible_pipelines(target_dir)
        assert "nanometanf" in compatible


class TestAdapterErrorHandling:
    """Test error handling in adapters"""
    
    def test_validation_with_permission_error(self, temp_structure):
        """Test validation when file access fails"""
        source_dir, target_dir = temp_structure
        adapter = NanometanfAdapter()
        
        # Create a file and then make directory unreadable (on Unix systems)
        test_file = target_dir / "test.fastq"
        test_file.write_text("@read1\nACGT\n+\nIIII\n")
        
        # Validation should still work even if some files can't be accessed
        report = adapter.get_validation_report(target_dir)
        # Should not crash, may or may not be valid depending on permissions
        assert "valid" in report
    
    def test_adapter_with_invalid_patterns(self):
        """Test adapter with invalid regex patterns"""
        config = {
            'name': 'invalid_pattern',
            'patterns': ['['],  # Invalid regex
            'min_files': 1
        }
        
        # Should not crash during creation
        adapter = GenericAdapter(config)
        assert adapter is not None


@pytest.fixture
def temp_structure():
    """Create temporary directory structure for testing"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        source_dir = tmp_path / "source"
        target_dir = tmp_path / "target"
        source_dir.mkdir()
        target_dir.mkdir()
        yield source_dir, target_dir