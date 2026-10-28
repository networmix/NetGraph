"""Read a nested value by its sequence of field names and indices."""


def at(value, path):
    for key in path:
        value = value[key]
    return value
