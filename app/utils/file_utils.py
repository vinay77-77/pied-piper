"""File utility functions for display formatting."""


def format_file_size(size_bytes: int) -> str:
    """Convert bytes to human-readable size string."""
    if size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    for unit in units:
        if size < 1024.0:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"


def format_speed(bytes_per_second: float) -> str:
    """Convert bytes/sec to human-readable speed string."""
    if bytes_per_second <= 0:
        return "0 B/s"
    units = ["B/s", "KB/s", "MB/s", "GB/s"]
    speed = float(bytes_per_second)
    for unit in units:
        if speed < 1024.0:
            if unit == "B/s":
                return f"{int(speed)} {unit}"
            return f"{speed:.1f} {unit}"
        speed /= 1024.0
    return f"{speed:.1f} TB/s"


def format_eta(seconds: float) -> str:
    """Convert seconds to human-readable ETA string."""
    if seconds <= 0:
        return "calculating..."
    if seconds < 60:
        return f"~{int(seconds)} sec remaining"
    if seconds < 3600:
        minutes = int(seconds / 60)
        secs = int(seconds % 60)
        return f"~{minutes} min {secs} sec remaining"
    hours = int(seconds / 3600)
    minutes = int((seconds % 3600) / 60)
    return f"~{hours} hr {minutes} min remaining"
