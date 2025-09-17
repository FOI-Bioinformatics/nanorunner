"""File system test fixtures and utilities.

This module provides fixtures for testing file system operations,
directory structures, and file handling edge cases.
"""

import pytest
import tempfile
import shutil
import stat
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from unittest.mock import MagicMock, patch, Mock
from contextlib import contextmanager


@pytest.fixture
def temp_directory_structure(tmp_path):
    """Create a temporary directory structure for testing.
    
    Creates a comprehensive directory structure with various file types
    and subdirectories for testing file operations.
    
    Returns:
        Path to root of temporary directory structure
    """
    root = tmp_path / "test_structure"
    root.mkdir()
    
    # Create subdirectories
    (root / "subdir1").mkdir()
    (root / "subdir2").mkdir()
    (root / "empty_dir").mkdir()
    
    # Create nested directories
    nested = root / "nested" / "deep" / "structure"
    nested.mkdir(parents=True)
    
    # Create various file types
    (root / "test.txt").write_text("Test content")
    (root / "test.fastq").write_text("@read1\nATCG\n+\nIIII\n")
    (root / "test.fq").write_text("@read2\nGCTA\n+\nIIII\n")
    (root / "subdir1" / "nested.fastq").write_text("@read3\nTTTT\n+\nIIII\n")
    (root / "subdir2" / "data.pod5").write_bytes(b"mock pod5 data")
    
    # Create hidden files
    (root / ".hidden").write_text("hidden content")
    (root / "subdir1" / ".hidden_fastq").write_text("@hidden\nAAAA\n+\nIIII\n")
    
    return root


@pytest.fixture
def readonly_directory(tmp_path):
    """Create a read-only directory for testing permission errors.
    
    Returns:
        Path to read-only directory
    """
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    
    # Create some files in the directory
    (readonly_dir / "readonly.txt").write_text("Read-only content")
    (readonly_dir / "readonly.fastq").write_text("@readonly\nCCCC\n+\nIIII\n")
    
    # Make directory read-only
    readonly_dir.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    
    yield readonly_dir
    
    # Cleanup: restore write permissions for cleanup
    try:
        readonly_dir.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
    except (OSError, PermissionError):
        pass


@pytest.fixture
def unicode_filenames(tmp_path):
    """Create files with unicode names for internationalization testing.
    
    Returns:
        Path to directory containing unicode filename test files
    """
    unicode_dir = tmp_path / "unicode_test"
    unicode_dir.mkdir()
    
    # Create files with various unicode characters
    unicode_files = [
        "测试文件.fastq",           # Chinese
        "файл_тест.fastq",         # Russian
        "αρχείο_δοκιμής.fastq",   # Greek
        "ファイル_テスト.fastq",    # Japanese
        "archivø_test.fastq",      # Danish
        "café_données.fq",         # French
        "niño_datos.fastq",        # Spanish
    ]
    
    for filename in unicode_files:
        try:
            file_path = unicode_dir / filename
            file_path.write_text(f"@unicode_test\nATCG\n+\nIIII\n# File: {filename}")
        except (OSError, UnicodeError):
            # Skip if filesystem doesn't support unicode
            continue
    
    return unicode_dir


@pytest.fixture
def mock_file_operations():
    """Mock file operations for testing error conditions and edge cases.
    
    Returns:
        Dictionary of mocked file operation functions
    """
    mocks = {}
    
    with (patch('shutil.copy2') as mock_copy,
          patch('shutil.move') as mock_move,
          patch('pathlib.Path.symlink_to') as mock_symlink,
          patch('pathlib.Path.mkdir') as mock_mkdir):
        
        mocks['copy'] = mock_copy
        mocks['move'] = mock_move
        mocks['symlink'] = mock_symlink
        mocks['mkdir'] = mock_mkdir
        
        # Configure default successful behavior
        mock_copy.return_value = None
        mock_move.return_value = None
        mock_symlink.return_value = None
        mock_mkdir.return_value = None
        
        yield mocks


@pytest.fixture
def slow_file_operations():
    """Mock file operations with artificial delays for performance testing.
    
    Returns:
        Context manager for slow file operations
    """
    import time
    
    original_copy = shutil.copy2
    original_move = shutil.move
    
    def slow_copy(src, dst, delay=0.1):
        time.sleep(delay)
        return original_copy(src, dst)
    
    def slow_move(src, dst, delay=0.1):
        time.sleep(delay)
        return original_move(src, dst)
    
    class SlowOperations:
        def __init__(self):
            self.copy_delay = 0.1
            self.move_delay = 0.1
            
        def set_copy_delay(self, delay):
            self.copy_delay = delay
            
        def set_move_delay(self, delay):
            self.move_delay = delay
        
        def __enter__(self):
            self.copy_patcher = patch('shutil.copy2', side_effect=lambda s, d: slow_copy(s, d, self.copy_delay))
            self.move_patcher = patch('shutil.move', side_effect=lambda s, d: slow_move(s, d, self.move_delay))
            
            self.copy_patcher.start()
            self.move_patcher.start()
            
            return self
        
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.copy_patcher.stop()
            self.move_patcher.stop()
    
    return SlowOperations()


# File system test utilities

class FileSystemTestHelper:
    """Helper class for file system testing operations."""
    
    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)
        self.created_paths = []
    
    def create_file(self, relative_path: str, content: str = "test content") -> Path:
        """Create a file with specified content."""
        file_path = self.base_path / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        self.created_paths.append(file_path)
        return file_path
    
    def create_fastq_file(self, relative_path: str, reads: int = 10) -> Path:
        """Create a FASTQ file with specified number of reads."""
        content = ""
        for i in range(reads):
            content += f"@read_{i:06d}\nATCGATCG\n+\nIIIIIIII\n"
        return self.create_file(relative_path, content)
    
    def create_directory(self, relative_path: str) -> Path:
        """Create a directory."""
        dir_path = self.base_path / relative_path
        dir_path.mkdir(parents=True, exist_ok=True)
        self.created_paths.append(dir_path)
        return dir_path
    
    def create_symlink(self, target_path: str, link_path: str) -> Path:
        """Create a symbolic link."""
        target = self.base_path / target_path
        link = self.base_path / link_path
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(target)
        self.created_paths.append(link)
        return link
    
    def get_created_paths(self) -> List[Path]:
        """Get list of all created paths."""
        return self.created_paths.copy()
    
    def cleanup(self):
        """Clean up all created paths."""
        for path in reversed(self.created_paths):
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except (OSError, FileNotFoundError):
                pass
        self.created_paths.clear()


@pytest.fixture
def file_system_helper(tmp_path):
    """Provide a file system test helper with automatic cleanup."""
    helper = FileSystemTestHelper(tmp_path)
    yield helper
    helper.cleanup()


# File permission testing utilities

@contextmanager
def temporary_permissions(path: Path, mode: int):
    """Temporarily change file/directory permissions."""
    original_mode = path.stat().st_mode
    try:
        path.chmod(mode)
        yield
    finally:
        try:
            path.chmod(original_mode)
        except (OSError, PermissionError):
            pass


@pytest.fixture
def permission_test_files(tmp_path):
    """Create files with various permission configurations for testing."""
    perm_dir = tmp_path / "permission_tests"
    perm_dir.mkdir()
    
    files = {}
    
    # Read-only file
    readonly_file = perm_dir / "readonly.fastq"
    readonly_file.write_text("@readonly\nATCG\n+\nIIII\n")
    readonly_file.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    files['readonly'] = readonly_file
    
    # Write-only file (if supported by filesystem)
    writeonly_file = perm_dir / "writeonly.fastq"
    writeonly_file.write_text("@writeonly\nATCG\n+\nIIII\n")
    try:
        writeonly_file.chmod(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        files['writeonly'] = writeonly_file
    except OSError:
        pass
    
    # No permissions file
    noperm_file = perm_dir / "noperm.fastq"
    noperm_file.write_text("@noperm\nATCG\n+\nIIII\n")
    try:
        noperm_file.chmod(0)
        files['noperm'] = noperm_file
    except OSError:
        pass
    
    yield files
    
    # Cleanup: restore permissions for removal
    for file_path in files.values():
        try:
            file_path.chmod(stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        except (OSError, PermissionError):
            pass


# Disk space testing utilities

class MockDiskSpace:
    """Mock disk space for testing space-related conditions."""
    
    def __init__(self, total: int = 1000000, used: int = 500000):
        self.total = total
        self.used = used
        self.free = total - used
    
    def set_free_space(self, free_bytes: int):
        """Set available free space."""
        self.free = free_bytes
        self.used = self.total - free_bytes
    
    def simulate_full_disk(self):
        """Simulate a full disk condition."""
        self.set_free_space(0)
    
    def simulate_low_space(self, threshold: int = 1000):
        """Simulate low disk space condition."""
        self.set_free_space(threshold)


@pytest.fixture
def mock_disk_space():
    """Provide mock disk space utilities for testing."""
    mock_space = MockDiskSpace()
    
    def mock_statvfs(path):
        """Mock statvfs system call."""
        mock_stat = MagicMock()
        mock_stat.f_frsize = 4096  # Fragment size
        mock_stat.f_blocks = mock_space.total // 4096
        mock_stat.f_bavail = mock_space.free // 4096
        mock_stat.f_bfree = mock_space.free // 4096
        return mock_stat
    
    with patch('os.statvfs', side_effect=mock_statvfs):
        yield mock_space


# File watching and monitoring utilities

class MockFileWatcher:
    """Mock file watcher for testing file monitoring."""
    
    def __init__(self):
        self.watched_paths = []
        self.events = []
        self.callbacks = []
    
    def watch(self, path: Path, callback=None):
        """Start watching a path."""
        self.watched_paths.append(path)
        if callback:
            self.callbacks.append(callback)
    
    def simulate_file_created(self, path: Path):
        """Simulate a file creation event."""
        event = {'type': 'created', 'path': path}
        self.events.append(event)
        for callback in self.callbacks:
            callback(event)
    
    def simulate_file_modified(self, path: Path):
        """Simulate a file modification event."""
        event = {'type': 'modified', 'path': path}
        self.events.append(event)
        for callback in self.callbacks:
            callback(event)
    
    def simulate_file_deleted(self, path: Path):
        """Simulate a file deletion event."""
        event = {'type': 'deleted', 'path': path}
        self.events.append(event)
        for callback in self.callbacks:
            callback(event)
    
    def get_events(self):
        """Get all simulated events."""
        return self.events.copy()
    
    def clear_events(self):
        """Clear all events."""
        self.events.clear()


@pytest.fixture
def mock_file_watcher():
    """Provide a mock file watcher for testing."""
    return MockFileWatcher()


# Edge case file utilities

def create_problematic_filenames(base_dir: Path) -> List[Path]:
    """Create files with problematic names for edge case testing."""
    problematic_files = []
    
    # Long filename (near filesystem limit)
    long_name = "a" * 240 + ".fastq"
    try:
        long_file = base_dir / long_name
        long_file.write_text("@long\nATCG\n+\nIIII\n")
        problematic_files.append(long_file)
    except OSError:
        pass
    
    # Files with special characters
    special_chars = ["file with spaces.fastq", "file-with-dashes.fastq", 
                    "file_with_underscores.fastq", "file.with.dots.fastq"]
    
    for filename in special_chars:
        try:
            file_path = base_dir / filename
            file_path.write_text("@special\nATCG\n+\nIIII\n")
            problematic_files.append(file_path)
        except OSError:
            pass
    
    return problematic_files


@pytest.fixture
def problematic_filenames(tmp_path):
    """Create files with problematic names for testing."""
    problem_dir = tmp_path / "problematic"
    problem_dir.mkdir()
    
    files = create_problematic_filenames(problem_dir)
    
    yield files
    
    # Cleanup
    for file_path in files:
        try:
            file_path.unlink()
        except (OSError, FileNotFoundError):
            pass