#!/usr/bin/env python3
"""
Pipeline Runner for Petrosa Realtime Strategies
Standardized CI/CD pipeline execution and testing
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Colors for output
class Colors:
    RED = "\033[0;31m"
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    PURPLE = "\033[0;35m"
    CYAN = "\033[0;36m"
    WHITE = "\033[1;37m"
    NC = "\033[0m"  # No Color


class PipelineRunner:
    """Standardized pipeline runner for Petrosa services"""

    def __init__(self, service_name: str = "realtime-strategies"):
        self.service_name = service_name
        self.start_time = datetime.now()
        self.results = {}
        self.errors = []
        self.warnings = []

    def log(self, message: str, level: str = "info"):
        """Log message with timestamp and color"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        color_map = {
            "info": Colors.BLUE,
            "success": Colors.GREEN,
            "warning": Colors.YELLOW,
            "error": Colors.RED,
            "header": Colors.PURPLE,
            "step": Colors.CYAN,
        }
        color = color_map.get(level, Colors.WHITE)
        print(f"{color}[{timestamp}] {message}{Colors.NC}")

    def run_command(
        self,
        command: list[str],
        description: str,
        capture_output: bool = False,
        check: bool = True,
    ) -> tuple[bool, str]:
        """Run a command and return success status and output"""
        self.log(f"🔄 {description}...", "step")

        try:
            if capture_output:
                result = subprocess.run(
                    command, capture_output=True, text=True, check=check, timeout=300
                )
                output = result.stdout + result.stderr
                success = result.returncode == 0
            else:
                result = subprocess.run(command, check=check, timeout=300)
                output = ""
                success = result.returncode == 0

            if success:
                self.log(f"✅ {description} completed successfully", "success")
            else:
                self.log(f"❌ {description} failed", "error")
                self.errors.append(f"{description}: {output}")

            return success, output

        except subprocess.TimeoutExpired:
            error_msg = f"{description} timed out after 5 minutes"
            self.log(f"⏰ {error_msg}", "error")
            self.errors.append(error_msg)
            return False, error_msg
        except subprocess.CalledProcessError as e:
            error_msg = (
                f"{description} failed with exit code {e.returncode}: {e.stderr}"
            )
            self.log(f"❌ {error_msg}", "error")
            self.errors.append(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"{description} failed with exception: {str(e)}"
            self.log(f"❌ {error_msg}", "error")
            self.errors.append(error_msg)
            return False, error_msg

    def check_prerequisites(self) -> bool:
        """Check if all prerequisites are met"""
        self.log("🔍 Checking prerequisites...", "header")

        prerequisites = [
            ("Python", ["python", "--version"]),
            ("pip", ["pip", "--version"]),
            ("Docker", ["docker", "--version"]),
            ("Make", ["make", "--version"]),
        ]

        all_good = True
        for name, command in prerequisites:
            success, output = self.run_command(
                command, f"Checking {name}", capture_output=True, check=False
            )
            if not success:
                all_good = False
                self.log(f"⚠️  {name} not found or not working", "warning")
            else:
                self.log(f"✅ {name} is available", "success")

        return all_good

    def setup_environment(self) -> bool:
        """Setup development environment"""
        self.log("🚀 Setting up environment...", "header")

        commands = [
            (["python", "-m", "pip", "install", "--upgrade", "pip"], "Upgrading pip"),
            (
                ["pip", "install", "-r", "requirements.txt"],
                "Installing production dependencies",
            ),
            (
                ["pip", "install", "-r", "requirements-dev.txt"],
                "Installing development dependencies",
            ),
        ]

        all_success = True
        for command, description in commands:
            success, _ = self.run_command(command, description)
            if not success:
                all_success = False

        return all_success

    def run_linting(self) -> bool:
        """Run code quality checks"""
        self.log("✨ Running code quality checks...", "header")

        commands = [
            (["make", "format"], "Code formatting"),
            (["make", "lint"], "Linting checks"),
            (["make", "type-check"], "Type checking"),
        ]

        all_success = True
        for command, description in commands:
            success, _ = self.run_command(command, description)
            if not success:
                all_success = False
                self.warnings.append(f"{description} failed")

        return all_success

    def run_tests(self) -> bool:
        """Run tests with coverage"""
        self.log("🧪 Running tests...", "header")

        success, output = self.run_command(
            ["make", "test"], "Running tests with coverage", capture_output=True
        )

        if success:
            # Extract coverage percentage
            try:
                for line in output.split("\n"):
                    if "TOTAL" in line and "%" in line:
                        coverage = line.split()[-1].replace("%", "")
                        self.results["coverage"] = float(coverage)
                        self.log(f"📊 Test coverage: {coverage}%", "success")
                        break
            except:
                self.log("⚠️  Could not extract coverage percentage", "warning")

        return success

    def run_security_scan(self) -> bool:
        """Run security scans"""
        self.log("🔒 Running security scans...", "header")

        success, _ = self.run_command(
            ["make", "security"], "Security scanning", capture_output=True
        )

        if not success:
            self.warnings.append("Security scan failed")

        return True  # Don't fail pipeline on security warnings

    def build_docker(self) -> bool:
        """Build Docker image"""
        self.log("🐳 Building Docker image...", "header")

        success, _ = self.run_command(["make", "build"], "Docker build")

        return success

    def test_container(self) -> bool:
        """Test Docker container"""
        self.log("📦 Testing Docker container...", "header")

        success, _ = self.run_command(["make", "container"], "Container testing")

        return success

    def deploy_to_k8s(self) -> bool:
        """Deploy to Kubernetes"""
        self.log("☸️  Deploying to Kubernetes...", "header")

        # Check if kubeconfig exists
        kubeconfig_path = Path("k8s/kubeconfig.yaml")
        if not kubeconfig_path.exists():
            self.log("⚠️  Kubeconfig not found, skipping deployment", "warning")
            self.warnings.append("Kubernetes deployment skipped - no kubeconfig")
            return True

        success, _ = self.run_command(["make", "deploy"], "Kubernetes deployment")

        return success

    def generate_report(self) -> dict:
        """Generate pipeline report"""
        end_time = datetime.now()
        duration = (end_time - self.start_time).total_seconds()

        report = {
            "service": self.service_name,
            "timestamp": self.start_time.isoformat(),
            "duration_seconds": duration,
            "success": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings,
            "results": self.results,
        }

        return report

    def save_report(self, report: dict, filename: str = None):
        """Save report to file"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"pipeline_report_{timestamp}.json"

        with open(filename, "w") as f:
            json.dump(report, f, indent=2)

        self.log(f"📄 Report saved to {filename}", "success")

    def print_summary(self, report: dict):
        """Print pipeline summary"""
        self.log("📋 Pipeline Summary", "header")
        print("=" * 50)

        print(f"Service: {report['service']}")
        print(f"Duration: {report['duration_seconds']:.2f} seconds")
        print(f"Status: {'✅ SUCCESS' if report['success'] else '❌ FAILED'}")

        if report["results"]:
            print("\nResults:")
            for key, value in report["results"].items():
                print(f"  {key}: {value}")

        if report["warnings"]:
            print(f"\n⚠️  Warnings ({len(report['warnings'])}):")
            for warning in report["warnings"]:
                print(f"  - {warning}")

        if report["errors"]:
            print(f"\n❌ Errors ({len(report['errors'])}):")
            for error in report["errors"]:
                print(f"  - {error}")

        print("=" * 50)

    def run_pipeline(self, stages: list[str] = None) -> bool:
        """Run the complete pipeline"""
        self.log(f"🚀 Starting {self.service_name} pipeline...", "header")

        if stages is None:
            stages = [
                "prerequisites",
                "setup",
                "linting",
                "tests",
                "security",
                "docker",
                "container",
                "deploy",
            ]

        stage_functions = {
            "prerequisites": self.check_prerequisites,
            "setup": self.setup_environment,
            "linting": self.run_linting,
            "tests": self.run_tests,
            "security": self.run_security_scan,
            "docker": self.build_docker,
            "container": self.test_container,
            "deploy": self.deploy_to_k8s,
        }

        for stage in stages:
            if stage not in stage_functions:
                self.log(f"⚠️  Unknown stage: {stage}", "warning")
                continue

            self.log(f"🔄 Running stage: {stage}", "step")
            success = stage_functions[stage]()

            if not success and stage in ["prerequisites", "setup", "tests", "docker"]:
                self.log(f"❌ Pipeline failed at stage: {stage}", "error")
                break

        # Generate and save report
        report = self.generate_report()
        self.save_report(report)
        self.print_summary(report)

        return report["success"]


def main():
    parser = argparse.ArgumentParser(
        description="Petrosa Realtime Strategies Pipeline Runner"
    )
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=[
            "prerequisites",
            "setup",
            "linting",
            "tests",
            "security",
            "docker",
            "container",
            "deploy",
        ],
        help="Pipeline stages to run",
    )
    parser.add_argument("--report", help="Output report filename")
    parser.add_argument("--service", default="realtime-strategies", help="Service name")

    args = parser.parse_args()

    runner = PipelineRunner(args.service)

    try:
        success = runner.run_pipeline(args.stages)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        runner.log("Pipeline interrupted by user", "warning")
        sys.exit(1)
    except Exception as e:
        runner.log(f"Pipeline failed with exception: {str(e)}", "error")
        sys.exit(1)


if __name__ == "__main__":
    main()
