"""Versioned prompt registry: loads YAML prompt files and resolves by (agent, version)."""
from pathlib import Path
import yaml
from config.settings import settings


class PromptRegistry:
    """Load and serve versioned agent prompts from YAML files."""

    def __init__(self, prompts_dir: str | None = None, version: str | None = None):
        self._dir = Path(prompts_dir or settings.prompts_dir)
        self._version = version or settings.prompt_version
        self._cache: dict[tuple[str, str], dict] = {}

    def get(self, agent_name: str, version: str | None = None) -> dict:
        """
        Return the prompt dict for the given agent and version.

        The YAML file must contain at least a `system` key.
        Optional keys: `user_template`, `description`.
        """
        ver = version or self._version
        key = (agent_name, ver)
        if key not in self._cache:
            path = self._dir / ver / f"{agent_name}.yaml"
            if not path.exists():
                raise FileNotFoundError(f"Prompt file not found: {path}")
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            self._cache[key] = data
        return self._cache[key]

    def get_system(self, agent_name: str, version: str | None = None) -> str:
        """Convenience: return only the system prompt string."""
        return self.get(agent_name, version)["system"]

    def list_versions(self, agent_name: str) -> list[str]:
        """Return all available versions for an agent."""
        versions = []
        for ver_dir in sorted(self._dir.iterdir()):
            if ver_dir.is_dir() and (ver_dir / f"{agent_name}.yaml").exists():
                versions.append(ver_dir.name)
        return versions

    def reload(self):
        """Clear cache to force reload from disk (useful after prompt edits)."""
        self._cache.clear()


# Module-level singleton
registry = PromptRegistry()
