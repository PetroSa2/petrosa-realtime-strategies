"""
Basic tests for strategies/main.py startup module.
"""


class TestMainModule:
    """Test main module functions."""

    def test_import_main(self):
        """Test that main module can be imported."""
        from strategies import main

        assert main is not None

    def test_main_has_app(self):
        """Test main module has app object."""
        from strategies import main

        assert hasattr(main, "app")

    def test_main_module_attributes(self):
        """Test that main module has expected attributes."""
        from strategies import main

        # Module should be importable and have basic structure
        assert main.__name__ == "strategies.main"

