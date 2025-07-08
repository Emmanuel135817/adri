#!/usr/bin/env python3
"""
Release preparation script for ADRI Validator.

This script automatically creates and manages draft releases with pre-filled
release notes based on the current version in pyproject.toml.

Features:
- Reads current version from pyproject.toml
- Calculates valid next release versions
- Creates/updates draft releases with templated notes
- Cleans up old draft releases
- Generates commit summaries since last release
- Uses GitHub CLI (gh) instead of requiring tokens
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class ReleasePreparator:
    """Manages automated release preparation for ADRI Validator."""

    def __init__(self):
        """Initialize the release preparator."""
        self.check_gh_cli()
        self.templates_dir = Path("templates/release-notes")

    def check_gh_cli(self):
        """Check if GitHub CLI is available and authenticated."""
        try:
            result = subprocess.run(
                ["gh", "auth", "status"], capture_output=True, text=True, check=False
            )
            if result.returncode != 0:
                raise RuntimeError(
                    "GitHub CLI not authenticated. Run 'gh auth login' first."
                )
        except FileNotFoundError:
            raise RuntimeError("GitHub CLI (gh) not found. Please install it first.")

    def run_gh_command(self, args: List[str]) -> str:
        """Run a GitHub CLI command and return the output."""
        try:
            result = subprocess.run(
                ["gh"] + args, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Warning: GitHub CLI command failed: {e}")
            print(f"Command: gh {' '.join(args)}")
            print(f"Error: {e.stderr}")
            return ""

    def get_current_version(self) -> str:
        """Get current version from pyproject.toml."""
        try:
            # Try to import tomllib (Python 3.11+)
            import tomllib
        except ImportError:
            try:
                # Fallback to tomli for older Python versions
                import tomli as tomllib
            except ImportError:
                # Manual parsing fallback
                pyproject_path = Path("pyproject.toml")
                if pyproject_path.exists():
                    with open(pyproject_path, "r") as f:
                        for line in f:
                            if line.strip().startswith('version = "'):
                                return line.split('"')[1]
                raise RuntimeError("Could not parse version from pyproject.toml")

        pyproject_path = Path("pyproject.toml")
        if not pyproject_path.exists():
            raise FileNotFoundError("pyproject.toml not found")

        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
            return data["project"]["version"]

    def parse_version(self, version: str) -> Tuple[int, int, int]:
        """Parse semantic version string into components."""
        pattern = r"^(\d+)\.(\d+)\.(\d+)"
        match = re.match(pattern, version)
        if not match:
            raise ValueError(f"Invalid version format: {version}")
        return tuple(map(int, match.groups()))

    def calculate_next_versions(self, current_version: str) -> Dict[str, str]:
        """Calculate all valid next version numbers."""
        major, minor, patch = self.parse_version(current_version)

        return {
            "patch": f"{major}.{minor}.{patch + 1}",
            "minor": f"{major}.{minor + 1}.0",
            "major": f"{major + 1}.0.0",
        }

    def get_commits_since_last_release(self, last_version: Optional[str]) -> List[Dict]:
        """Get commit messages since the last release."""
        try:
            # Get recent commits using gh CLI
            commits_output = self.run_gh_command(
                [
                    "api",
                    "repos/:owner/:repo/commits",
                    "--jq",
                    '.[0:10] | .[] | {sha: .sha[0:8], message: .commit.message | split("\\n")[0], author: .commit.author.name, date: .commit.author.date}',
                ]
            )

            if commits_output:
                commits = []
                for line in commits_output.split("\n"):
                    if line.strip():
                        try:
                            commit_data = json.loads(line)
                            commits.append(commit_data)
                        except json.JSONDecodeError:
                            continue
                return commits

            # Fallback: use git log
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--oneline",
                    "-10",
                    "--pretty=format:%h|%s|%an|%ad",
                    "--date=short",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            commits = []
            for line in result.stdout.strip().split("\n"):
                if line:
                    parts = line.split("|")
                    if len(parts) >= 4:
                        commits.append(
                            {
                                "sha": parts[0],
                                "message": parts[1],
                                "author": parts[2],
                                "date": parts[3],
                            }
                        )
            return commits

        except Exception as e:
            print(f"Warning: Could not fetch commits: {e}")
            return []

    def load_release_template(self, template_name: str) -> str:
        """Load release notes template from file."""
        template_path = self.templates_dir / f"{template_name}.md"
        if template_path.exists():
            with open(template_path, "r") as f:
                return f.read()

        # Fallback to default template
        return self.get_default_template()

    def get_default_template(self) -> str:
        """Get default release notes template."""
        return """## 🚀 ADRI Validator v{version} - {release_type} Release

### 📋 Release Information

• Type: {release_description}
• Previous Version: {previous_version}
• Installation: `pip install adri=={version}`

### ✨ What's New

{commit_summary}

### 🔧 Improvements

• Enhanced performance and reliability
• Updated dependencies for better compatibility
• Improved error messages and logging

### 🐛 Bug Fixes

•

### 📚 Documentation

• Updated README with new features
• Added usage examples
• Improved API documentation

### 🔧 Technical Details

• Python Support: 3.10, 3.11, 3.12
• Dependencies: Updated pandas to 1.5.0+
• Testing: 90%+ coverage maintained
• Performance: Optimized for large datasets

### 🔗 Links

• PyPI Package https://pypi.org/project/adri/{version}/
• TestPyPI Package https://test.pypi.org/project/adri/{version}/
• Documentation https://github.com/ThinkEvolveSolve/adri-validator/blob/main/README.md
• Changelog https://github.com/ThinkEvolveSolve/adri-validator/blob/main/CHANGELOG.md

### 🚀 Usage Example

```python
from adri import adri_protected

@adri_protected()
def your_ai_function(data):
    # Your AI/ML code here
    return processed_data
```

--------

Deployment Status: 🟡 Pending (will be updated automatically during release)
"""

    def generate_release_notes(
        self,
        version: str,
        release_type: str,
        previous_version: Optional[str],
        commits: List[Dict],
    ) -> str:
        """Generate complete release notes from template."""
        # Determine release description
        release_descriptions = {
            "patch": "Production Release (Patch) - Bug fixes and minor improvements",
            "minor": "Production Release (Minor) - New features, backward compatible",
            "major": "Production Release (Major) - Breaking changes and major updates",
            "beta-patch": "Beta Release (Patch) - Testing bug fixes",
            "beta-minor": "Beta Release (Minor) - Testing new features",
            "beta-major": "Beta Release (Major) - Testing breaking changes",
        }

        release_description = release_descriptions.get(
            release_type, "Production Release"
        )

        # Generate commit summary
        if commits:
            commit_lines = []
            for commit in commits[:8]:  # Limit to recent commits
                # Clean up commit message
                msg = commit["message"]
                if len(msg) > 60:
                    msg = msg[:57] + "..."
                commit_lines.append(f"• {msg} ({commit['sha']})")

            commit_summary = "Recent Changes:\n\n" + "\n".join(commit_lines)
            if len(commits) > 8:
                commit_summary += f"\n• ... and {len(commits) - 8} more commits"
        else:
            commit_summary = "• See commit history for detailed changes"

        # Load and format template
        template = self.load_release_template(release_type.replace("-", "_"))

        return template.format(
            version=version,
            release_type=release_type.replace("-", " ").title(),
            release_description=release_description,
            previous_version=previous_version or "None",
            commit_summary=commit_summary,
        )

    def cleanup_old_drafts(self):
        """Remove old draft releases to keep things clean."""
        try:
            # Get list of draft releases
            releases_output = self.run_gh_command(
                ["release", "list", "--json", "tagName,name,isDraft"]
            )

            if releases_output:
                releases = json.loads(releases_output)
                for release in releases:
                    if release.get("isDraft") and "ADRI v" in release.get("name", ""):
                        tag_name = release.get("tagName")
                        print(f"🧹 Cleaning up old draft: {release['name']}")
                        self.run_gh_command(["release", "delete", tag_name, "--yes"])
        except Exception as e:
            print(f"Warning: Could not cleanup old drafts: {e}")

    def create_or_update_draft(
        self, tag_name: str, title: str, body: str, prerelease: bool = False
    ):
        """Create or update a draft release."""
        try:
            # Check if draft already exists
            existing_releases = self.run_gh_command(
                ["release", "list", "--json", "tagName,name,isDraft"]
            )

            existing_draft = None
            if existing_releases:
                releases = json.loads(existing_releases)
                for release in releases:
                    if release.get("isDraft") and release.get("tagName") == tag_name:
                        existing_draft = release
                        break

            # Write body to temporary file to handle multiline content
            import tempfile

            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
                f.write(body)
                body_file = f.name

            try:
                if existing_draft:
                    print(f"📝 Updating existing draft: {title}")
                    cmd = [
                        "release",
                        "edit",
                        tag_name,
                        "--title",
                        title,
                        "--notes-file",
                        body_file,
                        "--draft",
                    ]
                    if prerelease:
                        cmd.append("--prerelease")
                    self.run_gh_command(cmd)
                else:
                    print(f"✨ Creating new draft: {title}")
                    cmd = [
                        "release",
                        "create",
                        tag_name,
                        "--title",
                        title,
                        "--notes-file",
                        body_file,
                        "--draft",
                    ]
                    if prerelease:
                        cmd.append("--prerelease")
                    self.run_gh_command(cmd)
            finally:
                # Clean up temporary file
                os.unlink(body_file)

        except Exception as e:
            print(f"Warning: Could not create/update draft {title}: {e}")

    def prepare_all_releases(self):
        """Prepare all release drafts."""
        print("🚀 Preparing ADRI Validator release drafts...")

        # Get current version
        current_version = self.get_current_version()
        next_versions = self.calculate_next_versions(current_version)

        commits = self.get_commits_since_last_release(current_version)

        print(f"📋 Current version: {current_version}")
        print(f"📝 Found {len(commits)} commits since last release")

        # Clean up old drafts first
        self.cleanup_old_drafts()

        # Create draft releases for each type
        release_types = [
            ("patch", "🔧 ADRI v{version} - Patch Release (DRAFT)", False),
            ("minor", "🚀 ADRI v{version} - Minor Release (DRAFT)", False),
            ("major", "💥 ADRI v{version} - Major Release (DRAFT)", False),
            ("beta-patch", "🧪 ADRI v{version} - Beta Patch (DRAFT)", True),
            ("beta-minor", "🧪 ADRI v{version} - Beta Minor (DRAFT)", True),
            ("beta-major", "🧪 ADRI v{version} - Beta Major (DRAFT)", True),
        ]

        for release_type, title_template, is_prerelease in release_types:
            if release_type.startswith("beta-"):
                base_type = release_type.replace("beta-", "")
                base_version = next_versions[base_type]
                version = base_version + "-beta.1"
                tag_name = f"candidate-{release_type}-v{base_version}"
            else:
                version = next_versions[release_type]
                tag_name = f"candidate-{release_type}-v{version}"

            title = title_template.format(version=version)
            body = self.generate_release_notes(
                version, release_type, current_version, commits
            )

            self.create_or_update_draft(tag_name, title, body, is_prerelease)

        print("✅ Release preparation completed!")
        print("📋 Check GitHub Releases for updated draft releases")
        print("🎯 Next steps:")
        print("   1. Go to GitHub Releases")
        print("   2. Select the appropriate draft release")
        print("   3. Edit release notes as needed")
        print("   4. Publish the release to trigger deployment")


def main():
    """Serve as main entry point."""
    try:
        preparator = ReleasePreparator()
        preparator.prepare_all_releases()
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
