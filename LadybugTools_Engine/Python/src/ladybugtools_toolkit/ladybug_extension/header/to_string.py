from ladybug.header import Header


def to_string(header: Header) -> str:
    """Convert a Ladybug header object into a string.

    Args:
        header (Header):
            A Ladybug header object.

    Returns:
        str:
            A Ladybug header string."""

    return f"{header.data_type} ({header.unit})"
