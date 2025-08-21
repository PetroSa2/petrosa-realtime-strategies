#!/bin/bash

# Development Setup Script for Petrosa Realtime Strategies
# Standardized development environment setup

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="realtime-strategies"
PYTHON_VERSION="3.11"

# Logging functions
log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Help function
show_help() {
    echo "🚀 Petrosa Realtime Strategies Development Setup"
    echo "==============================================="
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --python-version VERSION  Set Python version (default: 3.11)"
    echo "  --skip-docker            Skip Docker setup"
    echo "  --skip-k8s               Skip Kubernetes setup"
    echo "  --help                   Show this help message"
    echo ""
    echo "This script will:"
    echo "  1. Check system prerequisites"
    echo "  2. Setup Python environment"
    echo "  3. Install dependencies"
    echo "  4. Setup pre-commit hooks"
    echo "  5. Setup Docker (optional)"
    echo "  6. Setup Kubernetes (optional)"
    echo ""
}

# Check system prerequisites
check_prerequisites() {
    log_info "Checking system prerequisites..."
    
    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VER=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
        log_success "Python $PYTHON_VER found"
    else
        log_error "Python 3 not found. Please install Python $PYTHON_VERSION or later"
        exit 1
    fi
    
    # Check pip
    if command -v pip3 &> /dev/null; then
        log_success "pip3 found"
    else
        log_error "pip3 not found. Please install pip"
        exit 1
    fi
    
    # Check git
    if command -v git &> /dev/null; then
        log_success "git found"
    else
        log_error "git not found. Please install git"
        exit 1
    fi
    
    # Check make
    if command -v make &> /dev/null; then
        log_success "make found"
    else
        log_error "make not found. Please install make"
        exit 1
    fi
}

# Setup Python environment
setup_python() {
    log_info "Setting up Python environment..."
    
    # Upgrade pip
    log_info "Upgrading pip..."
    python3 -m pip install --upgrade pip
    
    # Install virtual environment if not exists
    if [ ! -d "venv" ]; then
        log_info "Creating virtual environment..."
        python3 -m venv venv
        log_success "Virtual environment created"
    else
        log_info "Virtual environment already exists"
    fi
    
    # Activate virtual environment
    log_info "Activating virtual environment..."
    source venv/bin/activate
    
    # Verify activation
    if [ "$VIRTUAL_ENV" != "" ]; then
        log_success "Virtual environment activated: $VIRTUAL_ENV"
    else
        log_error "Failed to activate virtual environment"
        exit 1
    fi
}

# Install dependencies
install_dependencies() {
    log_info "Installing dependencies..."
    
    # Install production dependencies
    log_info "Installing production dependencies..."
    pip install -r requirements.txt
    
    # Install development dependencies
    log_info "Installing development dependencies..."
    pip install -r requirements-dev.txt
    
    log_success "Dependencies installed successfully"
}

# Setup pre-commit hooks
setup_precommit() {
    log_info "Setting up pre-commit hooks..."
    
    # Install pre-commit
    pip install pre-commit
    
    # Install hooks
    pre-commit install
    
    log_success "Pre-commit hooks installed"
}

# Setup Docker
setup_docker() {
    log_info "Setting up Docker..."
    
    # Check if Docker is installed
    if command -v docker &> /dev/null; then
        log_success "Docker found"
        
        # Check if Docker daemon is running
        if docker info &> /dev/null; then
            log_success "Docker daemon is running"
        else
            log_warning "Docker daemon is not running. Please start Docker"
        fi
    else
        log_warning "Docker not found. Please install Docker for containerization"
        log_info "Visit: https://docs.docker.com/get-docker/"
    fi
}

# Setup Kubernetes
setup_kubernetes() {
    log_info "Setting up Kubernetes..."
    
    # Check if kubectl is installed
    if command -v kubectl &> /dev/null; then
        log_success "kubectl found"
        
        # Check if kubeconfig exists
        if [ -f "k8s/kubeconfig.yaml" ]; then
            log_success "Kubeconfig found"
            
            # Test connection
            export KUBECONFIG=k8s/kubeconfig.yaml
            if kubectl cluster-info --insecure-skip-tls-verify &> /dev/null; then
                log_success "Kubernetes cluster connection successful"
            else
                log_warning "Cannot connect to Kubernetes cluster"
            fi
        else
            log_warning "Kubeconfig not found at k8s/kubeconfig.yaml"
        fi
    else
        log_warning "kubectl not found. Please install kubectl for Kubernetes deployment"
        log_info "Visit: https://kubernetes.io/docs/tasks/tools/install-kubectl/"
    fi
}

# Create development configuration
create_dev_config() {
    log_info "Creating development configuration..."
    
    # Create .env file if not exists
    if [ ! -f ".env" ]; then
        log_info "Creating .env file..."
        cat > .env << EOF
# Development Environment Configuration
ENVIRONMENT=development
LOG_LEVEL=DEBUG

# NATS Configuration
NATS_URL=nats://localhost:4222
NATS_CONSUMER_TOPIC=market-data
NATS_PUBLISHER_TOPIC=trading-signals
NATS_CONSUMER_NAME=realtime-strategies-dev
NATS_CONSUMER_GROUP=strategies-group

# OpenTelemetry Configuration
ENABLE_OTEL=false
OTEL_SERVICE_VERSION=dev
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317
OTEL_METRICS_EXPORTER=none
OTEL_TRACES_EXPORTER=none
OTEL_LOGS_EXPORTER=none
EOF
        log_success ".env file created"
    else
        log_info ".env file already exists"
    fi
}

# Run initial tests
run_initial_tests() {
    log_info "Running initial tests..."
    
    # Run linting
    log_info "Running linting..."
    make lint || {
        log_warning "Linting failed - this is normal for initial setup"
    }
    
    # Run tests
    log_info "Running tests..."
    make test || {
        log_warning "Tests failed - this is normal for initial setup"
    }
    
    log_success "Initial tests completed"
}

# Main setup function
main_setup() {
    local skip_docker=false
    local skip_k8s=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --python-version)
                PYTHON_VERSION="$2"
                shift 2
                ;;
            --skip-docker)
                skip_docker=true
                shift
                ;;
            --skip-k8s)
                skip_k8s=true
                shift
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
    
    log_info "Starting development setup for $SERVICE_NAME..."
    echo "==============================================="
    
    # Run setup steps
    check_prerequisites
    echo ""
    
    setup_python
    echo ""
    
    install_dependencies
    echo ""
    
    setup_precommit
    echo ""
    
    if [ "$skip_docker" = false ]; then
        setup_docker
        echo ""
    else
        log_info "Skipping Docker setup"
    fi
    
    if [ "$skip_k8s" = false ]; then
        setup_kubernetes
        echo ""
    else
        log_info "Skipping Kubernetes setup"
    fi
    
    create_dev_config
    echo ""
    
    run_initial_tests
    echo ""
    
    log_success "Development setup completed successfully!"
    echo ""
    echo "🎉 Next steps:"
    echo "  1. Activate virtual environment: source venv/bin/activate"
    echo "  2. Run tests: make test"
    echo "  3. Start development: make run-local"
    echo "  4. Check status: make k8s-status"
    echo ""
    echo "📚 Useful commands:"
    echo "  make help          - Show all available commands"
    echo "  make pipeline      - Run complete CI/CD pipeline"
    echo "  make deploy        - Deploy to Kubernetes"
    echo "  ./scripts/bug-investigation.sh all - Run complete debugging"
    echo ""
}

# Run main setup
main_setup "$@"
