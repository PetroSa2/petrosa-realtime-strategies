# Petrosa Realtime Strategies Scripts

This directory contains automation scripts for the Petrosa Realtime Strategies service, following the standardized patterns used across all Petrosa services.

## Scripts Overview

### Core Scripts

- **`bug-investigation.sh`** - Comprehensive debugging and investigation tool
- **`run_pipeline.py`** - Complete CI/CD pipeline execution and testing
- **`setup-dev.sh`** - Development environment setup and configuration
- **`deploy-local.sh`** - Local deployment and testing procedures

### Usage Examples

#### Development Setup
```bash
# Complete development environment setup
./scripts/setup-dev.sh

# Setup without Docker/Kubernetes
./scripts/setup-dev.sh --skip-docker --skip-k8s
```

#### Bug Investigation
```bash
# Complete investigation
./scripts/bug-investigation.sh all

# Specific checks
./scripts/bug-investigation.sh k8s-status
./scripts/bug-investigation.sh k8s-logs
./scripts/bug-investigation.sh docker-build
```

#### Pipeline Execution
```bash
# Complete pipeline
python scripts/run_pipeline.py

# Specific stages
python scripts/run_pipeline.py --stages prerequisites setup linting tests
```

#### Local Deployment
```bash
# Complete local deployment
./scripts/deploy-local.sh all

# Individual steps
./scripts/deploy-local.sh build
./scripts/deploy-local.sh run --port 8081
./scripts/deploy-local.sh deploy
```

## Script Features

### Standardized Patterns
All scripts follow the Petrosa standard patterns:
- Consistent error handling and logging
- Color-coded output for better readability
- Comprehensive help documentation
- Integration with Makefile commands
- Kubernetes cluster compatibility (remote MicroK8s)

### Error Handling
- Graceful failure handling
- Detailed error messages
- Recovery suggestions
- Non-interactive operation

### Logging
- Timestamped output
- Color-coded log levels
- Structured information display
- Progress indicators

## Integration

### Makefile Integration
All scripts integrate with the main Makefile:
```bash
make pipeline      # Uses run_pipeline.py
make k8s-status    # Uses bug-investigation.sh
make deploy        # Uses deploy-local.sh
```

### Kubernetes Integration
- Remote MicroK8s cluster support
- Automatic kubeconfig detection
- Namespace management
- Resource cleanup

### Docker Integration
- Multi-architecture builds
- Local image testing
- Container health checks
- Resource cleanup

## Troubleshooting

### Common Issues

1. **Kubeconfig not found**
   - Ensure `k8s/kubeconfig.yaml` exists
   - Check file permissions
   - Verify cluster connectivity

2. **Docker build failures**
   - Check Docker daemon is running
   - Verify Dockerfile syntax
   - Check available disk space

3. **Python environment issues**
   - Activate virtual environment: `source venv/bin/activate`
   - Reinstall dependencies: `pip install -r requirements.txt`
   - Check Python version: `python --version`

### Debug Mode
Most scripts support verbose output:
```bash
# Enable debug output
export DEBUG=1
./scripts/bug-investigation.sh all
```

## Maintenance

### Script Updates
Scripts are automatically updated to match the latest Petrosa standards:
- Consistent with other services
- Latest security practices
- Updated dependencies
- Improved error handling

### Testing
All scripts are tested against:
- Local development environment
- Remote MicroK8s cluster
- Multiple Python versions
- Various failure scenarios

## Contributing

When adding new scripts:
1. Follow the existing patterns
2. Include comprehensive help documentation
3. Add proper error handling
4. Test with various scenarios
5. Update this README

## References

- [Petrosa Development Standards](../docs/DEVELOPMENT.md)
- [Kubernetes Deployment Guide](../docs/DEPLOYMENT.md)
- [CI/CD Pipeline Documentation](../docs/CI_CD.md)
