"""Realistic test data fixtures for nanopore sequencing simulation"""

import pytest
import tempfile
import gzip
import random
import string
from pathlib import Path
from typing import Dict, List, Tuple
import time


class RealisticDataGenerator:
    """Generate realistic nanopore sequencing test data"""
    
    @staticmethod
    def generate_realistic_fastq_read(read_id: str, length: int = None) -> str:
        """Generate a realistic FASTQ read with proper structure"""
        if length is None:
            # Shorter read lengths for faster testing
            length = random.choices(
                [100, 200, 500, 1000, 2000],
                weights=[40, 30, 20, 8, 2]
            )[0]
        
        # Generate realistic sequence with some bias towards certain bases
        bases = random.choices(
            ['A', 'T', 'G', 'C'],
            weights=[0.27, 0.27, 0.23, 0.23],  # Slight AT bias common in many genomes
            k=length
        )
        sequence = ''.join(bases)
        
        # Generate realistic quality scores (nanopore typically 7-40 range)
        # Most scores in mid-range with some low and high quality regions
        quality_chars = []
        for _ in range(length):
            if random.random() < 0.1:  # 10% low quality
                quality_chars.append(chr(33 + random.randint(7, 15)))
            elif random.random() < 0.2:  # 20% high quality  
                quality_chars.append(chr(33 + random.randint(35, 40)))
            else:  # 70% medium quality
                quality_chars.append(chr(33 + random.randint(20, 30)))
        
        quality = ''.join(quality_chars)
        
        return f"@{read_id}\n{sequence}\n+\n{quality}\n"
    
    @staticmethod
    def create_realistic_fastq_file(filepath: Path, num_reads: int = 1000, 
                                   compress: bool = False) -> Dict[str, any]:
        """Create a realistic FASTQ file with metadata"""
        
        reads = []
        total_bases = 0
        read_lengths = []
        
        for i in range(num_reads):
            read_id = f"read_{i:08d}_ch_{random.randint(1, 4000)}_strand_{random.choice([1, -1])}"
            read_length = random.choices(
                [500, 1000, 2000, 5000, 10000, 20000],
                weights=[25, 30, 20, 15, 8, 2]
            )[0]
            
            read = RealisticDataGenerator.generate_realistic_fastq_read(read_id, read_length)
            reads.append(read)
            total_bases += read_length
            read_lengths.append(read_length)
        
        content = ''.join(reads)
        
        if compress:
            with gzip.open(filepath, 'wt') as f:
                f.write(content)
        else:
            filepath.write_text(content)
        
        return {
            'num_reads': num_reads,
            'total_bases': total_bases,
            'mean_length': sum(read_lengths) / len(read_lengths),
            'min_length': min(read_lengths),
            'max_length': max(read_lengths),
            'file_size_mb': filepath.stat().st_size / (1024 * 1024),
            'compressed': compress
        }
    
    @staticmethod
    def create_realistic_pod5_file(filepath: Path, num_reads: int = 500) -> Dict[str, any]:
        """Create a mock POD5 file (binary format simulation)"""
        # POD5 files are binary, so we'll create a realistic-sized binary file
        # with some structure that mimics real POD5 characteristics
        
        # POD5 files are typically larger per read than FASTQ
        estimated_size = num_reads * random.randint(800, 1200)  # bytes per read
        
        # Generate semi-realistic binary content
        header = b'POD5\x00\x01\x00\x00'  # Mock header
        data = bytearray(header)
        
        for _ in range(estimated_size - len(header)):
            data.append(random.randint(0, 255))
        
        filepath.write_bytes(data)
        
        return {
            'num_reads': num_reads,
            'file_size_mb': filepath.stat().st_size / (1024 * 1024),
            'format': 'pod5'
        }


class RealisticSequencingScenarios:
    """Generate realistic sequencing run scenarios"""
    
    @staticmethod
    def create_minion_run(base_dir: Path, run_name: str = "minion_run") -> Dict[str, any]:
        """Create realistic MinION sequencing run structure"""
        run_dir = base_dir / run_name
        run_dir.mkdir()
        
        # Reduced for faster testing
        file_count = random.randint(10, 30)  # Much smaller for test speed
        total_reads = 0
        
        files_created = []
        
        for i in range(file_count):
            # Mix of file types and sizes
            if random.random() < 0.7:  # 70% FASTQ
                filename = f"reads_batch_{i:03d}.fastq"
                if random.random() < 0.3:  # 30% compressed
                    filename += ".gz"
                    
                filepath = run_dir / filename
                reads = random.randint(20, 100)  # Smaller for speed
                metadata = RealisticDataGenerator.create_realistic_fastq_file(
                    filepath, reads, filename.endswith('.gz')
                )
                total_reads += reads
                files_created.append((filepath, metadata))
            else:  # 30% POD5
                filepath = run_dir / f"signal_batch_{i:03d}.pod5"
                reads = random.randint(50, 500)
                metadata = RealisticDataGenerator.create_realistic_pod5_file(filepath, reads)
                total_reads += reads
                files_created.append((filepath, metadata))
        
        return {
            'run_type': 'minion',
            'run_dir': run_dir,
            'file_count': file_count,
            'total_reads': total_reads,
            'files': files_created,
            'estimated_runtime_hours': random.uniform(6, 48)
        }
    
    @staticmethod  
    def create_promethion_run(base_dir: Path, run_name: str = "promethion_run") -> Dict[str, any]:
        """Create realistic PromethION sequencing run structure"""
        run_dir = base_dir / run_name
        run_dir.mkdir()
        
        # Reduced for faster testing  
        file_count = random.randint(20, 50)
        total_reads = 0
        
        files_created = []
        
        for i in range(file_count):
            if random.random() < 0.8:  # 80% FASTQ for high-throughput
                filename = f"reads_batch_{i:04d}.fastq"
                if random.random() < 0.5:  # 50% compressed (higher for storage)
                    filename += ".gz"
                    
                filepath = run_dir / filename
                reads = random.randint(20, 50)  # Higher read counts
                metadata = RealisticDataGenerator.create_realistic_fastq_file(
                    filepath, reads, filename.endswith('.gz')
                )
                total_reads += reads
                files_created.append((filepath, metadata))
            else:
                filepath = run_dir / f"signal_batch_{i:04d}.pod5"
                reads = random.randint(10, 50)
                metadata = RealisticDataGenerator.create_realistic_pod5_file(filepath, reads)
                total_reads += reads
                files_created.append((filepath, metadata))
        
        return {
            'run_type': 'promethion',
            'run_dir': run_dir,
            'file_count': file_count,
            'total_reads': total_reads,
            'files': files_created,
            'estimated_runtime_hours': random.uniform(12, 72)
        }
    
    @staticmethod
    def create_multiplex_barcoded_run(base_dir: Path, num_barcodes: int = 12) -> Dict[str, any]:
        """Create realistic multiplexed barcoded sequencing run"""
        run_dir = base_dir / "barcoded_run"
        run_dir.mkdir()
        
        barcodes_data = {}
        total_files = 0
        total_reads = 0
        
        # Create barcode directories
        for bc_num in range(1, num_barcodes + 1):
            bc_dir = run_dir / f"barcode{bc_num:02d}"
            bc_dir.mkdir()
            
            # Each barcode gets very small amounts of data for fast testing
            files_in_barcode = random.randint(1, 3)  # Much fewer files per barcode
            barcode_reads = 0
            barcode_files = []
            
            for i in range(files_in_barcode):
                filename = f"reads_{i:03d}.fastq"
                if random.random() < 0.4:
                    filename += ".gz"
                
                filepath = bc_dir / filename
                reads = random.randint(50, 500)
                metadata = RealisticDataGenerator.create_realistic_fastq_file(
                    filepath, reads, filename.endswith('.gz')
                )
                barcode_reads += reads
                barcode_files.append((filepath, metadata))
            
            barcodes_data[f"barcode{bc_num:02d}"] = {
                'dir': bc_dir,
                'file_count': files_in_barcode,
                'total_reads': barcode_reads,
                'files': barcode_files
            }
            
            total_files += files_in_barcode
            total_reads += barcode_reads
        
        # Create unclassified directory
        unclass_dir = run_dir / "unclassified"
        unclass_dir.mkdir()
        unclass_files = random.randint(2, 5)
        unclass_reads = 0
        unclass_file_list = []
        
        for i in range(unclass_files):
            filepath = unclass_dir / f"unclassified_{i:03d}.fastq"
            reads = random.randint(20, 200)
            metadata = RealisticDataGenerator.create_realistic_fastq_file(filepath, reads)
            unclass_reads += reads
            unclass_file_list.append((filepath, metadata))
        
        barcodes_data['unclassified'] = {
            'dir': unclass_dir,
            'file_count': unclass_files,
            'total_reads': unclass_reads,
            'files': unclass_file_list
        }
        
        total_files += unclass_files
        total_reads += unclass_reads
        
        return {
            'run_type': 'multiplex',
            'run_dir': run_dir,
            'num_barcodes': num_barcodes,
            'total_files': total_files,
            'total_reads': total_reads,
            'barcodes': barcodes_data
        }


@pytest.fixture
def realistic_sequencing_data():
    """Pytest fixture for realistic sequencing data"""
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    
    yield {
        'temp_dir': temp_path,
        'generator': RealisticDataGenerator(),
        'scenarios': RealisticSequencingScenarios()
    }
    
    temp_dir.cleanup()


@pytest.fixture
def minion_run_fixture():
    """Specific fixture for MinION run testing"""
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    
    scenario = RealisticSequencingScenarios.create_minion_run(temp_path)
    
    yield scenario
    
    temp_dir.cleanup()


@pytest.fixture
def promethion_run_fixture():
    """Specific fixture for PromethION run testing"""
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    
    scenario = RealisticSequencingScenarios.create_promethion_run(temp_path)
    
    yield scenario
    
    temp_dir.cleanup()


@pytest.fixture
def multiplex_run_fixture():
    """Specific fixture for multiplexed run testing"""
    temp_dir = tempfile.TemporaryDirectory()
    temp_path = Path(temp_dir.name)
    
    # Create much smaller multiplex run for faster testing
    scenario = RealisticSequencingScenarios.create_multiplex_barcoded_run(temp_path, num_barcodes=3)
    
    yield scenario
    
    temp_dir.cleanup()