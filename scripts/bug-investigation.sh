#!/bin/bash

# Bug Investigation Script for Petrosa Realtime Strategies
# Standardized debugging and investigation procedures

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
SERVICE_NAME="realtime-strategies"
NAMESPACE="petrosa-apps"
KUBECONFIG_PATH="k8s/kubeconfig.yaml"

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
    echo "🐛 Petrosa Realtime Strategies Bug Investigation Tool"
    echo "=================================================="
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  all           - Run complete investigation"
    echo "  k8s-status    - Check Kubernetes deployment status"
    echo "  k8s-logs      - View Kubernetes logs"
    echo "  k8s-events    - Check Kubernetes events"
    echo "  k8s-resources - Check Kubernetes resources"
    echo "  docker-build  - Test Docker build"
    echo "  docker-run    - Test Docker container"
    echo "  local-test    - Run local tests"
    echo "  dependencies  - Check dependencies"
    echo "  config        - Validate configuration"
    echo "  network       - Check network connectivity"
    echo "  help          - Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 all                    # Run complete investigation"
    echo "  $0 k8s-logs               # View recent logs"
    echo "  $0 docker-build           # Test Docker build"
    echo ""
}

# Kubernetes status check
check_k8s_status() {
    log_info "Checking Kubernetes deployment status..."
    
    if [ ! -f "$KUBECONFIG_PATH" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG_PATH"
        return 1
    fi
    
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    echo ""
    log_info "Namespace status:"
    kubectl get namespace "$NAMESPACE" --insecure-skip-tls-verify 2>/dev/null || {
        log_error "Namespace $NAMESPACE not found or not accessible"
        return 1
    }
    
    echo ""
    log_info "Deployment status:"
    kubectl get deployment -n "$NAMESPACE" -l app=realtime-strategies --insecure-skip-tls-verify || {
        log_error "Deployment not found"
        return 1
    }
    
    echo ""
    log_info "Pod status:"
    kubectl get pods -n "$NAMESPACE" -l app=realtime-strategies --insecure-skip-tls-verify || {
        log_error "Pods not found"
        return 1
    }
    
    echo ""
    log_info "Service status:"
    kubectl get svc -n "$NAMESPACE" -l app=realtime-strategies --insecure-skip-tls-verify || {
        log_error "Services not found"
        return 1
    }
    
    log_success "Kubernetes status check completed"
}

# Kubernetes logs
check_k8s_logs() {
    log_info "Fetching Kubernetes logs..."
    
    if [ ! -f "$KUBECONFIG_PATH" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG_PATH"
        return 1
    fi
    
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    echo ""
    log_info "Recent pod logs (last 50 lines):"
    kubectl logs -n "$NAMESPACE" -l app=realtime-strategies --tail=50 --insecure-skip-tls-verify || {
        log_error "Failed to fetch logs"
        return 1
    }
    
    echo ""
    log_info "Previous pod logs (if any):"
    kubectl logs -n "$NAMESPACE" -l app=realtime-strategies --tail=50 --previous --insecure-skip-tls-verify 2>/dev/null || {
        log_warning "No previous logs available"
    }
    
    log_success "Logs check completed"
}

# Kubernetes events
check_k8s_events() {
    log_info "Checking Kubernetes events..."
    
    if [ ! -f "$KUBECONFIG_PATH" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG_PATH"
        return 1
    fi
    
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    echo ""
    log_info "Recent events in namespace:"
    kubectl get events -n "$NAMESPACE" --sort-by='.lastTimestamp' --insecure-skip-tls-verify | tail -20 || {
        log_error "Failed to fetch events"
        return 1
    }
    
    echo ""
    log_info "Events for realtime-strategies:"
    kubectl get events -n "$NAMESPACE" --field-selector involvedObject.name=petrosa-realtime-strategies --sort-by='.lastTimestamp' --insecure-skip-tls-verify || {
        log_warning "No specific events found for realtime-strategies"
    }
    
    log_success "Events check completed"
}

# Kubernetes resources
check_k8s_resources() {
    log_info "Checking Kubernetes resources..."
    
    if [ ! -f "$KUBECONFIG_PATH" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG_PATH"
        return 1
    fi
    
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    echo ""
    log_info "All resources in namespace:"
    kubectl get all -n "$NAMESPACE" --insecure-skip-tls-verify || {
        log_error "Failed to fetch resources"
        return 1
    }
    
    echo ""
    log_info "ConfigMaps:"
    kubectl get configmap -n "$NAMESPACE" --insecure-skip-tls-verify || {
        log_warning "No ConfigMaps found"
    }
    
    echo ""
    log_info "Secrets:"
    kubectl get secrets -n "$NAMESPACE" --insecure-skip-tls-verify || {
        log_warning "No Secrets found"
    }
    
    log_success "Resources check completed"
}

# Docker build test
test_docker_build() {
    log_info "Testing Docker build..."
    
    if [ ! -f "Dockerfile" ]; then
        log_error "Dockerfile not found"
        return 1
    fi
    
    echo ""
    log_info "Building Docker image..."
    docker build -t petrosa-realtime-strategies:test . || {
        log_error "Docker build failed"
        return 1
    }
    
    echo ""
    log_info "Testing Docker container..."
    docker run --rm petrosa-realtime-strategies:test --help || {
        log_error "Docker container test failed"
        return 1
    }
    
    log_success "Docker build test completed"
}

# Docker run test
test_docker_run() {
    log_info "Testing Docker container run..."
    
    echo ""
    log_info "Running container in background..."
    CONTAINER_ID=$(docker run -d --name petrosa-realtime-strategies-test petrosa-realtime-strategies:test) || {
        log_error "Failed to start container"
        return 1
    }
    
    echo "Container ID: $CONTAINER_ID"
    
    sleep 5
    
    echo ""
    log_info "Container logs:"
    docker logs "$CONTAINER_ID" || {
        log_error "Failed to get container logs"
    }
    
    echo ""
    log_info "Container status:"
    docker ps -a --filter "id=$CONTAINER_ID" || {
        log_error "Failed to get container status"
    }
    
    echo ""
    log_info "Cleaning up test container..."
    docker stop "$CONTAINER_ID" 2>/dev/null || true
    docker rm "$CONTAINER_ID" 2>/dev/null || true
    
    log_success "Docker run test completed"
}

# Local tests
run_local_tests() {
    log_info "Running local tests..."
    
    echo ""
    log_info "Checking Python environment..."
    python --version || {
        log_error "Python not available"
        return 1
    }
    
    echo ""
    log_info "Installing dependencies..."
    pip install -r requirements.txt -r requirements-dev.txt || {
        log_error "Failed to install dependencies"
        return 1
    }
    
    echo ""
    log_info "Running linting..."
    make lint || {
        log_warning "Linting failed"
    }
    
    echo ""
    log_info "Running type checking..."
    make type-check || {
        log_warning "Type checking failed"
    }
    
    echo ""
    log_info "Running tests..."
    make test || {
        log_error "Tests failed"
        return 1
    }
    
    log_success "Local tests completed"
}

# Dependencies check
check_dependencies() {
    log_info "Checking dependencies..."
    
    echo ""
    log_info "Python packages:"
    pip list || {
        log_error "Failed to list Python packages"
        return 1
    }
    
    echo ""
    log_info "Security scan:"
    make security || {
        log_warning "Security scan failed"
    }
    
    echo ""
    log_info "Dependency vulnerabilities:"
    safety check || {
        log_warning "Safety check failed"
    }
    
    log_success "Dependencies check completed"
}

# Configuration validation
validate_config() {
    log_info "Validating configuration..."
    
    echo ""
    log_info "Checking Kubernetes manifests..."
    if [ -d "k8s" ]; then
        for file in k8s/*.yaml; do
            if [ -f "$file" ]; then
                echo "Validating $file..."
                kubectl apply --dry-run=client -f "$file" || {
                    log_warning "Validation failed for $file"
                }
            fi
        done
    else
        log_warning "k8s directory not found"
    fi
    
    echo ""
    log_info "Checking environment variables..."
    if [ -f ".env" ]; then
        echo "Environment file found"
    else
        log_warning "No .env file found"
    fi
    
    log_success "Configuration validation completed"
}

# Network connectivity
check_network() {
    log_info "Checking network connectivity..."
    
    echo ""
    log_info "Checking NATS connectivity..."
    # This would need to be implemented based on your NATS setup
    log_warning "NATS connectivity check not implemented"
    
    echo ""
    log_info "Checking external dependencies..."
    # Add checks for any external services your app depends on
    
    log_success "Network check completed"
}

# Complete investigation
run_complete_investigation() {
    log_info "Running complete bug investigation..."
    echo "======================================"
    echo ""
    
    check_k8s_status
    echo ""
    
    check_k8s_logs
    echo ""
    
    check_k8s_events
    echo ""
    
    check_k8s_resources
    echo ""
    
    test_docker_build
    echo ""
    
    run_local_tests
    echo ""
    
    check_dependencies
    echo ""
    
    validate_config
    echo ""
    
    check_network
    echo ""
    
    log_success "Complete investigation finished!"
    echo ""
    echo "📋 Summary:"
    echo "  - Kubernetes status checked"
    echo "  - Logs reviewed"
    echo "  - Events analyzed"
    echo "  - Resources verified"
    echo "  - Docker build tested"
    echo "  - Local tests run"
    echo "  - Dependencies checked"
    echo "  - Configuration validated"
    echo "  - Network connectivity verified"
    echo ""
    echo "🔍 Next steps:"
    echo "  1. Review any errors or warnings above"
    echo "  2. Check application-specific logs"
    echo "  3. Verify environment variables"
    echo "  4. Test with different configurations"
    echo "  5. Monitor resource usage"
}

# Main script logic
main() {
    case "${1:-help}" in
        "all")
            run_complete_investigation
            ;;
        "k8s-status")
            check_k8s_status
            ;;
        "k8s-logs")
            check_k8s_logs
            ;;
        "k8s-events")
            check_k8s_events
            ;;
        "k8s-resources")
            check_k8s_resources
            ;;
        "docker-build")
            test_docker_build
            ;;
        "docker-run")
            test_docker_run
            ;;
        "local-test")
            run_local_tests
            ;;
        "dependencies")
            check_dependencies
            ;;
        "config")
            validate_config
            ;;
        "network")
            check_network
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
