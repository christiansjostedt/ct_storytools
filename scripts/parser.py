# config_parser.py
# Fixed: Continuations outside if='=', finalize outside loop. Added sub-dict per SHOT keyed by NAME for multiples.
def parse_config(file_path: str) -> dict:
    """
    Parse the configuration file into a nested structure with globals.
    ... (docstring unchanged)
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()
    globals_dict = {}
    current_shot = {}
    multi_line_value = ''
    current_key = None
    in_global_section = True
    shots_temp = []  # Temporary list to collect raw shots before nesting
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        i += 1
        if not stripped:
            if current_key is not None:
                multi_line_value += '\n' + line.rstrip()
            continue
        if stripped.startswith('#'):
            continue
        if stripped == '!---------':
            # Finalize current key if any
            if current_key is not None:
                final_value = multi_line_value.strip()
                if in_global_section:
                    globals_dict[current_key] = final_value
                else:
                    current_shot[current_key] = final_value
                multi_line_value = ''
                current_key = None
            # If in shot section, store raw shot
            if not in_global_section and current_shot:  # Avoid empty
                shots_temp.append(current_shot.copy())
                current_shot = {}
            # Switch to shot section
            in_global_section = False
            continue
        # Line with possible =
        if '=' in stripped:
            # Finalize previous
            if current_key is not None:
                final_value = multi_line_value.strip()
                if in_global_section:
                    globals_dict[current_key] = final_value
                else:
                    current_shot[current_key] = final_value
                multi_line_value = ''
                current_key = None
            parts = stripped.split('=', 1)
            key = parts[0].strip()
            if len(parts) > 1:
                value = parts[1].strip()
                if value:
                    if in_global_section:
                        globals_dict[key] = value
                    else:
                        current_shot[key] = value
                else:
                    # Start multi-line for empty value
                    current_key = key
                    multi_line_value = ''
            # Malformed: ignore
        else:
            # Continuation line (no =, has content) - FIXED: Now outside if='='
            if current_key is not None:
                multi_line_value += '\n' + line.rstrip()
            elif stripped:  # Standalone content (e.g., synopsis body)
                if in_global_section:
                    if 'SYNOPSIS' not in globals_dict:  # Assume starts new if no current
                        globals_dict['SYNOPSIS'] = stripped
                    else:
                        globals_dict['SYNOPSIS'] += '\n' + stripped
                else:
                    if 'SYNOPSIS' not in current_shot:
                        current_shot['SYNOPSIS'] = stripped
                    else:
                        current_shot['SYNOPSIS'] += '\n' + stripped
    # Finalize last section (after loop)
    if current_key is not None:
        final_value = multi_line_value.strip()
        if in_global_section:
            globals_dict[current_key] = final_value
        else:
            current_shot[current_key] = final_value
    if not in_global_section and current_shot:
        shots_temp.append(current_shot.copy())
    # Build nested structure
    project_name = globals_dict.get('PROJECT', 'default').strip()
    config = {'globals': globals_dict}
    config[project_name] = {}
    for shot in shots_temp:
        sequence = shot.get('SEQUENCE', 'unknown')
        shot_id = shot.get('SHOT', 'unknown')  # Primary identifier
        subshot_id = shot.get('NAME', 'unnamed')  # Unique per shot under SHOT
        merged_shot = globals_dict.copy()
        merged_shot.update(shot)
        if sequence not in config[project_name]:
            config[project_name][sequence] = {}
        if shot_id not in config[project_name][sequence]:
            config[project_name][sequence][shot_id] = {}
        config[project_name][sequence][shot_id][subshot_id] = merged_shot
    return config

