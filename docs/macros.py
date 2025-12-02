"""
MkDocs macros for generating parameter documentation from nextflow_schema.json.

This module is used by mkdocs-macros-plugin to dynamically generate
parameter tables from the Nextflow schema, keeping docs in sync with the pipeline.
"""

import json
from pathlib import Path


def define_env(env):
    """Define macros for MkDocs."""

    @env.macro
    def render_params_from_schema(schema_path: str = "nextflow_schema.json", show_hidden: bool = False):
        """
        Render all parameter groups from the Nextflow schema as markdown tables.

        Args:
            schema_path: Path to the nextflow_schema.json file (relative to repo root)
            show_hidden: Whether to include hidden parameters

        Returns:
            Markdown string with all parameter tables
        """
        # Find the schema file - try multiple locations
        possible_paths = [
            Path(env.project_dir) / schema_path,           # docs/nextflow_schema.json
            Path(env.project_dir).parent / schema_path,    # ./nextflow_schema.json (repo root)
            Path(schema_path),                              # absolute or cwd-relative
        ]

        schema_file = None
        for p in possible_paths:
            if p.exists():
                schema_file = p
                break

        if schema_file is None:
            return f"**Error**: Schema file not found. Tried: {[str(p) for p in possible_paths]}"

        with open(schema_file) as f:
            schema = json.load(f)

        output = []

        # Get the order of groups from allOf
        group_order = []
        for ref in schema.get("allOf", []):
            ref_path = ref.get("$ref", "")
            if ref_path.startswith("#/$defs/"):
                group_order.append(ref_path.replace("#/$defs/", ""))

        # Process each group in order
        defs = schema.get("$defs", {})
        for group_key in group_order:
            if group_key not in defs:
                continue

            group = defs[group_key]

            # Skip institutional config (usually not user-facing)
            if group_key == "institutional_config_options":
                continue

            title = group.get("title", group_key.replace("_", " ").title())
            description = group.get("description", "")
            properties = group.get("properties", {})
            required = group.get("required", [])

            if not properties:
                continue

            # Filter hidden params unless requested
            visible_params = {
                k: v for k, v in properties.items()
                if show_hidden or not v.get("hidden", False)
            }

            if not visible_params:
                continue

            output.append(f"## {title}\n")
            if description:
                output.append(f"{description}\n")

            # Build table
            output.append("| Parameter | Description | Default | Required |")
            output.append("| :-------- | :---------- | :------ | :------- |")

            for param_name, param_info in visible_params.items():
                desc = param_info.get("description", "")

                # Add help_text as expandable details if present
                help_text = param_info.get("help_text", "")
                if help_text:
                    desc += f"<br><details><summary>Help</summary>{help_text}</details>"

                # Format default value
                default = param_info.get("default", "")
                if default == "":
                    default_str = ""
                elif isinstance(default, bool):
                    default_str = f"`{str(default).lower()}`"
                elif isinstance(default, (int, float)):
                    default_str = f"`{default}`"
                else:
                    default_str = f"`{default}`"

                # Check if required
                is_required = param_name in required
                required_str = "Yes" if is_required else ""

                output.append(f"| `--{param_name}` | {desc} | {default_str} | {required_str} |")

            output.append("")  # Empty line after table

        return "\n".join(output)

    @env.macro
    def render_param_group(group_name: str, schema_path: str = "nextflow_schema.json"):
        """
        Render a single parameter group from the schema.

        Args:
            group_name: The key of the group in $defs (e.g., "input_output_options")
            schema_path: Path to the nextflow_schema.json file

        Returns:
            Markdown string with the parameter table for that group
        """
        possible_paths = [
            Path(env.project_dir) / schema_path,
            Path(env.project_dir).parent / schema_path,
            Path(schema_path),
        ]

        schema_file = None
        for p in possible_paths:
            if p.exists():
                schema_file = p
                break

        if schema_file is None:
            return f"**Error**: Schema file not found"

        with open(schema_file) as f:
            schema = json.load(f)

        defs = schema.get("$defs", {})
        if group_name not in defs:
            return f"**Error**: Group `{group_name}` not found in schema"

        group = defs[group_name]
        properties = group.get("properties", {})
        required = group.get("required", [])

        # Filter hidden params
        visible_params = {
            k: v for k, v in properties.items()
            if not v.get("hidden", False)
        }

        if not visible_params:
            return "*No visible parameters in this group.*"

        output = []
        output.append("| Parameter | Description | Default | Required |")
        output.append("| :-------- | :---------- | :------ | :------- |")

        for param_name, param_info in visible_params.items():
            desc = param_info.get("description", "")
            help_text = param_info.get("help_text", "")
            if help_text:
                desc += f"<br><details><summary>Help</summary>{help_text}</details>"

            default = param_info.get("default", "")
            if default == "":
                default_str = ""
            elif isinstance(default, bool):
                default_str = f"`{str(default).lower()}`"
            elif isinstance(default, (int, float)):
                default_str = f"`{default}`"
            else:
                default_str = f"`{default}`"

            is_required = param_name in required
            required_str = "Yes" if is_required else ""

            output.append(f"| `--{param_name}` | {desc} | {default_str} | {required_str} |")

        return "\n".join(output)
