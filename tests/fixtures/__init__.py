"""Test fixtures and utilities for NanoRunner testing.

This package provides reusable test fixtures, utilities, and data creation
functions for comprehensive testing of the NanoRunner nanopore simulator.

Modules:
    data_fixtures: Test data creation and management utilities
    config_fixtures: Configuration and setup fixtures
    monitoring_fixtures: Monitoring and progress tracking test utilities
    file_fixtures: File system and data structure test utilities
"""

from .data_fixtures import (
    # Test data creation utilities
    create_test_fastq_content,
    create_test_pod5_content,
    create_realistic_fastq,
    create_compressed_fastq,
    
    # Directory structure fixtures
    singleplex_test_data,
    multiplex_test_data,
    mixed_test_data,
    empty_test_data,
    
    # Performance test data
    large_test_dataset,
    small_test_dataset,
)

from .config_fixtures import (
    # Configuration fixtures
    basic_config,
    parallel_config,
    monitoring_config,
    profile_configs,
    
    # Timing model fixtures
    uniform_timing_config,
    random_timing_config,
    poisson_timing_config,
    adaptive_timing_config,
)

from .monitoring_fixtures import (
    # Monitoring utilities
    mock_progress_monitor,
    mock_resource_monitor,
    mock_signal_handler,
    
    # Monitoring test utilities
    monitoring_test_context,
    capture_monitoring_output,
)

from .file_fixtures import (
    # File system utilities
    temp_directory_structure,
    readonly_directory,
    unicode_filenames,
    
    # File operation utilities
    mock_file_operations,
    slow_file_operations,
)

__all__ = [
    # Data fixtures
    'create_test_fastq_content',
    'create_test_pod5_content',
    'create_realistic_fastq',
    'create_compressed_fastq',
    'singleplex_test_data',
    'multiplex_test_data',
    'mixed_test_data',
    'empty_test_data',
    'large_test_dataset',
    'small_test_dataset',
    
    # Config fixtures
    'basic_config',
    'parallel_config',
    'monitoring_config',
    'profile_configs',
    'uniform_timing_config',
    'random_timing_config',
    'poisson_timing_config',
    'adaptive_timing_config',
    
    # Monitoring fixtures
    'mock_progress_monitor',
    'mock_resource_monitor',
    'mock_signal_handler',
    'monitoring_test_context',
    'capture_monitoring_output',
    
    # File fixtures
    'temp_directory_structure',
    'readonly_directory',
    'unicode_filenames',
    'mock_file_operations',
    'slow_file_operations',
]