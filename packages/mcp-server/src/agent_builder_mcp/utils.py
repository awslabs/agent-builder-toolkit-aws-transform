import importlib.metadata


def get_package_version() -> str:
    """Get package version from pip metadata."""
    try:
        return importlib.metadata.version("atx-agent-builder-mcp")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0"
