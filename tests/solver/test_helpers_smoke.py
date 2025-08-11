def test_import_solver_helpers_module() -> None:
    import ngraph.solver.helpers as helpers

    assert hasattr(helpers, "__doc__")
