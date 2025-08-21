#!/bin/bash

# Local Deployment Script for Petrosa Realtime Strategies
# Standardized local deployment and testing procedures

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
DOCKER_IMAGE="petrosa-realtime-strategies:local"

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
    echo "🚀 Petrosa Realtime Strategies Local Deployment"
    echo "=============================================="
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  build         - Build Docker image locally"
    echo "  run           - Run service locally"
    echo "  deploy        - Deploy to local Kubernetes"
    echo "  test          - Run local tests"
    echo "  clean         - Clean up local resources"
    echo "  all           - Run complete local deployment"
    echo "  help          - Show this help message"
    echo ""
    echo "Options:"
    echo "  --image IMAGE     Docker image name (default: petrosa-realtime-strategies:local)"
    echo "  --namespace NS    Kubernetes namespace (default: petrosa-apps)"
    echo "  --port PORT       Local port for service (default: 8080)"
    echo "  --env ENV         Environment file (default: .env)"
    echo ""
    echo "Examples:"
    echo "  $0 build                    # Build Docker image"
    echo "  $0 run --port 8081          # Run locally on port 8081"
    echo "  $0 deploy                   # Deploy to Kubernetes"
    echo "  $0 all                      # Complete local deployment"
    echo ""
}

# Build Docker image
build_image() {
    log_info "Building Docker image..."
    
    if [ ! -f "Dockerfile" ]; then
        log_error "Dockerfile not found"
        return 1
    fi
    
    # Build image
    docker build -t "$DOCKER_IMAGE" . || {
        log_error "Docker build failed"
        return 1
    }
    
    log_success "Docker image built successfully: $DOCKER_IMAGE"
}

# Run service locally
run_local() {
    local port="${1:-8080}"
    local env_file="${2:-.env}"
    
    log_info "Running service locally on port $port..."
    
    # Check if image exists
    if ! docker image inspect "$DOCKER_IMAGE" &> /dev/null; then
        log_warning "Docker image not found, building..."
        build_image
    fi
    
    # Create container name
    local container_name="petrosa-realtime-strategies-local"
    
    # Stop existing container if running
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true
    
    # Run container
    local docker_args=(
        "-d"
        "--name" "$container_name"
        "-p" "$port:8080"
        "--env-file" "$env_file"
    )
    
    # Add additional environment variables
    docker_args+=(
        "-e" "ENVIRONMENT=local"
        "-e" "LOG_LEVEL=DEBUG"
    )
    
    docker run "${docker_args[@]}" "$DOCKER_IMAGE" || {
        log_error "Failed to start container"
        return 1
    }
    
    log_success "Service started successfully"
    log_info "Container: $container_name"
    log_info "Port: http://localhost:$port"
    log_info "Logs: docker logs -f $container_name"
}

# Deploy to local Kubernetes
deploy_k8s() {
    log_info "Deploying to local Kubernetes..."
    
    # Check if kubeconfig exists
    if [ ! -f "$KUBECONFIG_PATH" ]; then
        log_error "Kubeconfig not found at $KUBECONFIG_PATH"
        return 1
    fi
    
    export KUBECONFIG="$KUBECONFIG_PATH"
    
    # Check if namespace exists
    if ! kubectl get namespace "$NAMESPACE" --insecure-skip-tls-verify &> /dev/null; then
        log_info "Creating namespace $NAMESPACE..."
        kubectl create namespace "$NAMESPACE" --insecure-skip-tls-verify || {
            log_error "Failed to create namespace"
            return 1
        }
    fi
    
    # Update image in deployment
    log_info "Updating deployment with local image..."
    
    # Create temporary deployment file
    local temp_deployment="k8s/deployment-local.yaml"
    cp k8s/deployment.yaml "$temp_deployment"
    
    # Replace image
    sed -i.bak "s|yurisa2/petrosa-realtime-strategies:VERSION_PLACEHOLDER|$DOCKER_IMAGE|g" "$temp_deployment"
    
    # Apply deployment
    kubectl apply -f "$temp_deployment" -n "$NAMESPACE" --insecure-skip-tls-verify || {
        log_error "Failed to apply deployment"
        rm -f "$temp_deployment" "$temp_deployment.bak"
        return 1
    }
    
    # Clean up temporary files
    rm -f "$temp_deployment" "$temp_deployment.bak"
    
    # Wait for deployment to be ready
    log_info "Waiting for deployment to be ready..."
    kubectl rollout status deployment/petrosa-realtime-strategies -n "$NAMESPACE" --timeout=300s --insecure-skip-tls-verify || {
        log_error "Deployment failed to become ready"
        return 1
    }
    
    log_success "Deployment successful"
    
    # Show deployment status
    log_info "Deployment status:"
    kubectl get pods -n "$NAMESPACE" -l app=realtime-strategies --insecure-skip-tls-verify
    kubectl get svc -n "$NAMESPACE" -l app=realtime-strategies --insecure-skip-tls-verify
}

# Run local tests
run_tests() {
    log_info "Running local tests..."
    
    # Run unit tests
    log_info "Running unit tests..."
    make test || {
        log_error "Unit tests failed"
        return 1
    }
    
    # Run integration tests if available
    if [ -d "tests/integration" ]; then
        log_info "Running integration tests..."
        pytest tests/integration/ -v || {
            log_warning "Integration tests failed"
        }
    fi
    
    # Run Docker tests
    log_info "Testing Docker container..."
    docker run --rm "$DOCKER_IMAGE" --help || {
        log_error "Docker container test failed"
        return 1
    }
    
    log_success "Local tests completed"
}

# Clean up local resources
cleanup() {
    log_info "Cleaning up local resources..."
    
    # Stop and remove local container
    local container_name="petrosa-realtime-strategies-local"
    docker stop "$container_name" 2>/dev/null || true
    docker rm "$container_name" 2>/dev/null || true
    
    # Remove local image
    docker rmi "$DOCKER_IMAGE" 2>/dev/null || true
    
    # Clean up Kubernetes resources
    if [ -f "$KUBECONFIG_PATH" ]; then
        export KUBECONFIG="$KUBECONFIG_PATH"
        log_info "Cleaning up Kubernetes resources..."
        kubectl delete deployment petrosa-realtime-strategies -n "$NAMESPACE" --insecure-skip-tls-verify 2>/dev/null || true
        kubectl delete svc petrosa-realtime-strategies-service -n "$NAMESPACE" --insecure-skip-tls-verify 2>/dev/null || true
    fi
    
    # Clean up temporary files
    rm -f k8s/deployment-local.yaml k8s/deployment-local.yaml.bak
    
    log_success "Cleanup completed"
}

# Complete local deployment
run_all() {
    log_info "Running complete local deployment..."
    echo "======================================"
    echo ""
    
    # Build image
    build_image
    echo ""
    
    # Run tests
    run_tests
    echo ""
    
    # Deploy to Kubernetes
    deploy_k8s
    echo ""
    
    log_success "Complete local deployment finished!"
    echo ""
    echo "📋 Summary:"
    echo "  - Docker image built: $DOCKER_IMAGE"
    echo "  - Tests passed"
    echo "  - Deployed to Kubernetes namespace: $NAMESPACE"
    echo ""
    echo "🔍 Next steps:"
    echo "  1. Check deployment: kubectl get pods -n $NAMESPACE --insecure-skip-tls-verify"
    echo "  2. View logs: kubectl logs -n $NAMESPACE -l app=realtime-strategies --insecure-skip-tls-verify"
    echo "  3. Test service: kubectl port-forward -n $NAMESPACE svc/petrosa-realtime-strategies-service 8080:80"
    echo "  4. Clean up: $0 clean"
    echo ""
}

# Main script logic
main() {
    local command="${1:-help}"
    local port="8080"
    local env_file=".env"
    
    # Parse options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --image)
                DOCKER_IMAGE="$2"
                shift 2
                ;;
            --namespace)
                NAMESPACE="$2"
                shift 2
                ;;
            --port)
                port="$2"
                shift 2
                ;;
            --env)
                env_file="$2"
                shift 2
                ;;
            *)
                command="$1"
                shift
                ;;
        esac
    done
    
    case "$command" in
        "build")
            build_image
            ;;
        "run")
            run_local "$port" "$env_file"
            ;;
        "deploy")
            deploy_k8s
            ;;
        "test")
            run_tests
            ;;
        "clean")
            cleanup
            ;;
        "all")
            run_all
            ;;
        "help"|*)
            show_help
            ;;
    esac
}

# Run main function with all arguments
main "$@"
