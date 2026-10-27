"""Declaration locations for workflow refusals at load and preparation."""

from ngraph.utils.values import _bounded, _shown

_MISSING = object()


def workflow_location(index, name=None):
    location = f"workflow[{index}]"
    if isinstance(name, str):
        plain = str.__str__(name)
        if plain:
            location += f" (name {_shown(plain)})"
    return location


def workflow_error(location, value=_MISSING, reason="", field=""):
    path = location + ("." + _bounded(field, 100) if field else "")
    shown = "" if value is _MISSING else f" = {_shown(value)}"
    return ValueError(f"{path}{shown}: {_bounded(reason)}")


def error_context(exc, labels, fields=()):
    """Take a field only from an owned boundary label or the refusing reader's metadata.
    Keep the reason after that label, else the whole message minus one leading boundary record label."""
    label = getattr(exc, "_input_label", None)
    field = getattr(exc, "_workflow_field", "")
    owned = hasattr(exc, "_workflow_field")
    if not owned and label is not None:
        if label in fields:
            field, owned = label, True
        elif label in {
            "workflow step " + key
            for key in ("name", "seed", "yaml_label", "derived_seed")
        }:
            field, owned = label.removeprefix("workflow step "), True
        else:
            for prefix in labels:
                if label.startswith(prefix + "."):
                    field, owned = label[len(prefix) :].lstrip("."), True
                    break
    message = str(exc)
    if owned:
        if label and message.startswith(label + ": "):
            return field, exc._input_reason
        message = exc._input_reason
    for prefix in labels[:1]:
        if message.startswith(prefix + ": "):
            return field, message[len(prefix) + 2 :]
    return field, message


def workflow_declared(location, raw, build, *labels):
    try:
        return build()
    except (ValueError, TypeError, KeyError) as exc:
        field, message = error_context(exc, labels, fields=raw)
        if field:
            raw = raw.get(field, getattr(exc, "_input_value", raw))
        raise workflow_error(location, raw, message, field) from exc
