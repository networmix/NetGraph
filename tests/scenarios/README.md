# NetGraph Integration Testing Framework

## Overview

This directory contains integration testing utilities for NetGraph scenarios. The framework provides modular utilities for validating network topologies, blueprint expansions, failure policies, traffic demands, and flow results.

## Architecture

### Core Components

#### 1. **helpers.py** - Core Testing Utilities
- **ScenarioTestHelper**: Main validation class with modular test methods
- **NetworkExpectations**: Structured expectations for network validation
- **ScenarioDataBuilder**: Builder pattern for programmatic scenario creation
- **ScenarioValidationConfig**: Configuration for selective validation control

#### 2. **expectations.py** - Test Expectations Data
- **SCENARIO_*_EXPECTATIONS**: Predefined expectations for each test scenario
- **Validation constants**: Reusable constants for consistent validation
- **Helper functions**: Calculations for topology expectations

#### 3. **test_data_templates.py** - Composable Templates
- **NetworkTemplates**: Common topology patterns (linear, star, mesh, ring, tree)
- **BlueprintTemplates**: Reusable blueprint patterns for hierarchies
- **FailurePolicyTemplates**: Standard failure scenario configurations
- **TrafficDemandTemplates**: Traffic demand patterns and distributions
- **WorkflowTemplates**: Common analysis workflow configurations
- **ScenarioTemplateBuilder**: High-level builder for complete scenarios
- **CommonScenarios**: Pre-built scenarios for typical use cases

### Test Scenarios

#### Scenario 1: Basic L3 Backbone Network
- **Purpose**: Validates fundamental NetGraph capabilities
- **Features**: 6-node topology, explicit links, single failure policies
- **Complexity**: Basic

#### Scenario 2: Hierarchical DSL with Blueprints
- **Purpose**: Tests blueprint system and parameter overrides
- **Features**: Nested blueprints, mesh patterns, parameter customization
- **Complexity**: Advanced

#### Scenario 3: 3-tier CLOS Network
- **Purpose**: Validates NetGraph features with nested blueprints
- **Features**: Deep nesting, capacity probing, node/link overrides
- **Complexity**: Expert

## Key Features

### Modular Validation
```python
helper = ScenarioTestHelper(scenario)
helper.set_graph(built_graph)
helper.validate_network_structure(expectations)
helper.validate_topology_semantics()
helper.validate_flow_results("step_name", "flow_label", expected_value)
```

### Structured Expectations
```python
SCENARIO_1_EXPECTATIONS = NetworkExpectations(
    node_count=6,
    edge_count=20,  # 10 physical links * 2 directed edges
    specific_nodes={"SEA", "SFO", "DEN", "DFW", "JFK", "DCA"},
    blueprint_expansions={},  # No blueprints in scenario 1
)
```

### Template-based Scenario Creation
```python
scenario = (ScenarioTemplateBuilder("test_network", "1.0")
    .with_linear_backbone(["A", "B", "C"], link_capacity=100.0)
    .with_uniform_traffic(["A", "C"], demand_value=50.0)
    .with_single_link_failures()
    .with_capacity_analysis("A", "C")
    .build())
```

### Error Validation
- Malformed YAML handling
- Blueprint reference validation
- Traffic demand correctness
- Failure policy configuration
- Edge case coverage

## Best Practices

### Test Organization
1. Use fixtures for common scenario setups
2. Validate incrementally from basic structure to flows
3. Group related tests in focused test classes
4. Provide clear error messages with context

### Validation Approach
1. Start with structural validation (node/edge counts)
2. Verify specific elements (expected nodes/links)
3. Check semantic correctness (topology properties)
4. Validate business logic (flow results, policies)

### Template Usage
1. Prefer templates over manual scenario construction
2. Compose templates for scenarios
3. Use constants for configuration values
4. Document template parameters clearly

## Code Quality Standards

### Documentation
- Module and class docstrings
- Parameter and return value documentation
- Usage examples in docstrings
- Clear error message context

### Type Safety
- Type annotations for all functions
- Optional parameter handling
- Generic type usage where appropriate
- Union types for flexible interfaces

### Error Handling
- Descriptive error messages with context
- Input validation with clear feedback
- Graceful handling of edge cases
- Appropriate exception types

### Maintainability
- Constants for magic numbers
- Modular, focused methods
- Consistent naming conventions
- Separated concerns (validation vs data creation)

## Usage Examples

### Basic Scenario Validation
```python
def test_my_scenario():
    scenario = load_scenario_from_file("my_scenario.yaml")
    scenario.run()

    helper = create_scenario_helper(scenario)
    graph = scenario.results.get("build_graph", "graph")
    helper.set_graph(graph)

    # Validate structure
    expectations = NetworkExpectations(node_count=5, edge_count=8)
    helper.validate_network_structure(expectations)

    # Validate semantics
    helper.validate_topology_semantics()
```

### Template-based Scenario Creation
```python
def test_custom_topology():
    builder = ScenarioDataBuilder()
    scenario = (builder
        .with_simple_nodes(["Hub", "Spoke1", "Spoke2"])
        .with_simple_links([("Hub", "Spoke1", 10), ("Hub", "Spoke2", 10)])
        .with_traffic_demand("Spoke1", "Spoke2", 5.0)
        .with_workflow_step("BuildGraph", "build_graph")
        .build_scenario())

    scenario.run()
    # ... validation ...
```

### Blueprint Testing
```python
def test_blueprint_expansion():
    helper = create_scenario_helper(scenario)
    helper.set_graph(built_graph)

    # Validate blueprint created expected nodes
    helper.validate_blueprint_expansions(NetworkExpectations(
        blueprint_expansions={
            "datacenter_east/spine/": 4,
            "datacenter_east/leaf/": 8,
        }
    ))
```

## Recent Improvements

### Enhanced Organization
- Separated test expectations into dedicated module
- Improved file structure and imports
- Better separation of concerns

### Documentation
- Module and method documentation
- Usage examples and best practices
- Clear parameter descriptions

### Code Quality
- Added validation constants and thresholds
- Enhanced error messages with context
- Better type annotations and safety

### Templates
- More composable template system
- Safety limits for large networks
- Consistent parameter interfaces

### Validation
- Improved connectivity analysis
- Enhanced attribute validation
- Better flow conservation checks

## Contributing

When adding new test scenarios or validation methods:

1. Follow naming conventions established in existing code
2. Add documentation with usage examples
3. Include type annotations for all new functions
4. Write focused, modular tests that can be easily understood
5. Update expectations in the dedicated expectations.py file
6. Add templates for reusable patterns

## Testing

Run all integration tests:
```bash
pytest tests/scenarios/ -v
```

Run specific scenario tests:
```bash
pytest tests/scenarios/test_scenario_1.py -v
```

Run template examples:
```bash
pytest tests/scenarios/test_template_examples.py -v
```

This framework provides integration testing for NetGraph while maintaining code quality, readability, and maintainability standards.

## Template Usage Guidelines

### Consistent Template Usage Strategy

The integration tests framework follows a **hybrid approach** for template usage:

#### 1. **Main Scenario Tests** (test_scenario_*.py)
- **Primary**: Use `load_scenario_from_file()` with static YAML files
- **Rationale**: These serve as integration references and demonstrate real-world usage
- **Template Variants**: Also include template-based variants for testing different configurations

#### 2. **Error Case Tests** (test_error_cases.py)
- **Primary**: Use `ScenarioDataBuilder` and template builders consistently
- **Rationale**: Easier to create invalid configurations programmatically
- **Raw YAML**: Only for syntax errors that builders cannot create

#### 3. **Template Examples** (test_template_examples.py)
- **Primary**: Full template system usage with all template classes
- **Rationale**: Demonstrates template capabilities and validates template system

### Template Selection Guide

| Test Type | Recommended Approach | Example |
|-----------|---------------------|---------|
| Basic Integration | YAML files + template variants | `test_scenario_1.py` |
| Error Cases | Template builders | `ErrorInjectionTemplates.missing_nodes_builder()` |
| Edge Cases | Template builders | `EdgeCaseTemplates.empty_network_builder()` |
| Performance Tests | Template builders | `PerformanceTestTemplates.large_star_network_builder()` |
| Parameterized Tests | Template builders | `ScenarioTemplateBuilder` with loops |

### Template Builder Categories

#### **ErrorInjectionTemplates**
```python
# For testing invalid configurations
builder = ErrorInjectionTemplates.circular_blueprint_builder()
scenario = builder.build_scenario()
with pytest.raises((ValueError, RecursionError)):
    scenario.run()
```

#### **EdgeCaseTemplates**
```python
# For boundary conditions and edge cases
builder = EdgeCaseTemplates.zero_capacity_links_builder()
scenario = builder.build_scenario()
scenario.run()  # Should handle gracefully
```

#### **PerformanceTestTemplates**
```python
# For stress testing and performance validation
builder = PerformanceTestTemplates.large_star_network_builder(leaf_count=500)
scenario = builder.build_scenario()
scenario.run()  # Performance test
```

#### **ScenarioTemplateBuilder**
```python
# For high-level scenario composition
scenario_yaml = (ScenarioTemplateBuilder("test", "1.0")
    .with_linear_backbone(["A", "B", "C"])
    .with_uniform_traffic(["A", "C"], 25.0)
    .with_single_link_failures()
    .build())
```

### Best Practices

#### **DO: Use Templates For**
- ✅ Error case testing with invalid configurations
- ✅ Parameterized tests with different scales
- ✅ Edge case and boundary condition testing
- ✅ Performance and stress testing
- ✅ Rapid prototyping of test scenarios

#### **DON'T: Use Templates For**
- ❌ Replacing existing YAML-based integration tests
- ❌ Simple one-off tests where YAML is clearer
- ❌ Tests that need exact YAML syntax validation

#### **Template Composition**
```python
# Combine multiple template categories
def test_complex_error_scenario():
    builder = ErrorInjectionTemplates.negative_demand_builder()
    # Add additional edge case conditions
    builder.data["network"]["links"].extend(
        EdgeCaseTemplates.zero_capacity_links_builder().data["network"]["links"]
    )
    scenario = builder.build_scenario()
    # Test error handling with multiple conditions
```

#### **Consistent Error Testing**
```python
# Standard pattern for error case tests
def test_missing_blueprint():
    builder = ErrorInjectionTemplates.circular_blueprint_builder()
    with pytest.raises((ValueError, RecursionError)):
        scenario = builder.build_scenario()
        scenario.run()
```

### Migration Guide

#### **Existing Tests**
- Keep existing YAML-based tests as integration references
- Add template-based variants for parameterized testing
- Migrate error cases to use template builders

#### **New Tests**
- Start with appropriate template builder
- Use `ScenarioTemplateBuilder` for high-level composition
- Use specialized templates for specific test categories

### Template Development

#### **Adding New Templates**
1. Choose appropriate template class (Error/EdgeCase/Performance)
2. Follow existing naming conventions (`*_builder()` methods)
3. Return `ScenarioDataBuilder` instances for consistency
4. Add comprehensive docstrings with usage examples

#### **Template Testing**
- Each template should have validation tests
- Test both successful scenario building and execution
- Verify template produces expected network structures
