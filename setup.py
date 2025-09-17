"""Setup script for nanorunner package"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text(encoding="utf-8") if readme_path.exists() else ""

setup(
    name="nanorunner",
    version="2.0.0",
    author="FOI Bioinformatics",
    author_email="bioinformatics@foi.se",
    description="Comprehensive nanopore sequencing simulator with timing models, parallel processing, and real-time monitoring for bioinformatics pipeline testing",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/FOI-Bioinformatics/nanorunner",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    keywords="nanopore sequencing bioinformatics simulation oxford-nanopore fastq pod5 timing-models parallel-processing real-time-monitoring pipeline-testing nanometanf",
    python_requires=">=3.7",
    install_requires=[
        # No external dependencies - uses only standard library
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov",
            "black",
            "flake8",
            "mypy",
        ],
        "test": [
            "pytest>=6.0",
            "pytest-cov",
        ],
        "enhanced": [
            "psutil>=5.8.0",  # For resource monitoring
        ],
    },
    entry_points={
        "console_scripts": [
            "nanorunner=nanopore_simulator.cli.main:main",
        ],
    },
    project_urls={
        "Bug Reports": "https://github.com/FOI-Bioinformatics/nanorunner/issues",
        "Source": "https://github.com/FOI-Bioinformatics/nanorunner",
        "Documentation": "https://github.com/FOI-Bioinformatics/nanorunner#readme",
    },
    include_package_data=True,
    zip_safe=False,
)