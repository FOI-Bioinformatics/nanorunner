# Security Policy

## Supported Versions

We release patches for security vulnerabilities in the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 2.0.x   | :white_check_mark: |
| 1.0.x   | :x:                |

## Reporting a Vulnerability

The NanoRunner team takes security bugs seriously. We appreciate your efforts to responsibly disclose your findings and will make every effort to acknowledge your contributions.

### How to Report a Security Vulnerability

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to:

**Email**: bioinformatics@foi.se

**Subject**: [SECURITY] NanoRunner Vulnerability Report

### What to Include in Your Report

To help us better understand the nature and scope of the potential issue, please include as much information as possible:

- **Type of issue** (e.g., buffer overflow, SQL injection, cross-site scripting, etc.)
- **Full paths of source file(s)** related to the manifestation of the issue
- **Location** of the affected source code (tag/branch/commit or direct URL)
- **Step-by-step instructions** to reproduce the issue
- **Proof-of-concept or exploit code** (if possible)
- **Impact** of the issue, including how an attacker might exploit it

### What to Expect

After you submit a report, you can expect:

1. **Acknowledgment**: We will acknowledge receipt of your vulnerability report within **3 business days**.

2. **Assessment**: We will investigate and validate the vulnerability within **7 days** and provide an initial assessment.

3. **Resolution**:
   - **Critical vulnerabilities**: Patch released within 7-14 days
   - **High severity**: Patch released within 14-30 days
   - **Medium/Low severity**: Patch released in next scheduled release

4. **Disclosure**: We will work with you to understand and resolve the issue before any public disclosure. We ask that you:
   - Allow us **90 days** to investigate and respond
   - Avoid exploiting the vulnerability beyond necessary verification
   - Do not publicly disclose the vulnerability until it has been addressed

5. **Credit**: If you wish, we will publicly acknowledge your responsible disclosure in:
   - The security advisory
   - CHANGELOG.md
   - Release notes

### Security Updates

Security advisories will be published in:
- GitHub Security Advisories
- CHANGELOG.md with `[SECURITY]` tag
- GitHub Releases

Subscribe to the repository to receive notifications about security updates.

## Security Best Practices

When using NanoRunner, follow these security best practices:

### File System Security

1. **Validate source directories**: Ensure source directories are from trusted sources
   ```bash
   # Check directory permissions before simulation
   ls -la /path/to/source
   ```

2. **Use restricted permissions**: Run simulations with minimal required permissions
   ```bash
   # Avoid running as root
   nanorunner /source /target --operation copy
   ```

3. **Symlink safety**: When using `--operation link`, be aware of symlink vulnerabilities
   ```bash
   # Symlinks can point outside intended directories
   # Use with caution in untrusted environments
   ```

### Configuration Security

1. **Validate file paths**: Always use absolute paths when possible
   ```python
   from pathlib import Path
   source = Path("/trusted/source").resolve()
   target = Path("/trusted/target").resolve()
   ```

2. **Resource limits**: Set appropriate worker counts to prevent resource exhaustion
   ```bash
   # Limit parallel workers on shared systems
   nanorunner /source /target --parallel --worker-count 4
   ```

3. **Monitor resource usage**: Use enhanced monitoring to detect anomalies
   ```bash
   nanorunner /source /target --monitor enhanced
   ```

### Dependency Security

1. **Keep dependencies updated**: Regularly update to latest stable versions
   ```bash
   pip install --upgrade nanorunner[enhanced]
   ```

2. **Verify installations**: Check package signatures and hashes when possible
   ```bash
   pip install --require-hashes nanorunner
   ```

3. **Use virtual environments**: Isolate NanoRunner from system Python
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install nanorunner
   ```

## Known Security Considerations

### File Operations

- **Symlink following**: The simulator follows symlinks by default. In untrusted environments, this could potentially expose files outside the intended directory tree.

- **Disk space**: Large-scale simulations can consume significant disk space. Ensure adequate monitoring to prevent disk exhaustion.

- **Memory usage**: Parallel processing can consume significant memory. Set appropriate `worker-count` limits.

### Code Execution

- **No eval() or exec()**: NanoRunner does not use dynamic code execution.

- **No shell injection**: All file operations use Path objects and safe system calls.

- **Configuration validation**: All user inputs are validated before use.

## Scope

### In Scope

- Path traversal vulnerabilities
- Resource exhaustion (disk, memory, CPU)
- Configuration injection
- Privilege escalation
- Data leakage through logs or monitoring

### Out of Scope

- Vulnerabilities in dependencies (report to respective projects)
- Social engineering attacks
- Physical access attacks
- Denial of service through network-level attacks
- Issues in third-party bioinformatics pipelines

## Security Contacts

For urgent security issues:

- **Email**: bioinformatics@foi.se
- **Response time**: 3 business days maximum
- **Encryption**: PGP key available on request

For general security questions or discussions:
- GitHub Discussions
- GitHub Issues (non-sensitive topics only)

Thank you for helping keep NanoRunner and its users safe!
