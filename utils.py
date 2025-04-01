def human_size(size):
    """
    Convert a size in bytes to a human-readable format.
    """
    suffixes = ['B', 'KB', 'MB', 'GB', 'TB']
    for i, s in enumerate(suffixes):
        unit = 1024 ** (i + 2)
        if size < unit:
            return f"{1024 * size / unit:.1f} {s}"
    return f"{1024 * size / unit:.1f} {s}"