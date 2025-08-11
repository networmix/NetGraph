def test_import_failure_manager_helper_modules() -> None:
    import ngraph.failure.manager.aggregate as agg
    import ngraph.failure.manager.enumerate as enum
    import ngraph.failure.manager.simulate as sim

    assert isinstance(agg.__doc__, str)
    assert isinstance(enum.__doc__, str)
    assert isinstance(sim.__doc__, str)
