# config_parser.py
# Updated: support FLUX_HOST, WAN_HOST, QWEN_HOST (comma-separated lists)

def parse_config(file_path: str) -> dict:
    """
    Parse the configuration file into a nested structure with globals.
    Now splits FLUX_HOST, WAN_HOST, QWEN_HOST into lists if comma-separated.
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
            if not in_global_section and current_shot:
                shots_temp.append(current_shot.copy())
                current_shot = {}

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
                    # Start multi-line
                    current_key = key
                    multi_line_value = ''
            # else: malformed → ignore

        else:
            # Continuation line
            if current_key is not None:
                multi_line_value += '\n' + line.rstrip()
            elif stripped:
                if in_global_section:
                    if 'SYNOPSIS' not in globals_dict:
                        globals_dict['SYNOPSIS'] = stripped
                    else:
                        globals_dict['SYNOPSIS'] += '\n' + stripped
                else:
                    if 'SYNOPSIS' not in current_shot:
                        current_shot['SYNOPSIS'] = stripped
                    else:
                        current_shot['SYNOPSIS'] += '\n' + stripped

    # Finalize last multi-line if open
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
        sequence   = shot.get('SEQUENCE', 'unknown')
        shot_id    = shot.get('SHOT',     'unknown')
        subshot_id = shot.get('NAME',     'unnamed')

        merged_shot = globals_dict.copy()
        merged_shot.update(shot)

        if sequence not in config[project_name]:
            config[project_name][sequence] = {}
        if shot_id not in config[project_name][sequence]:
            config[project_name][sequence][shot_id] = {}

        config[project_name][sequence][shot_id][subshot_id] = merged_shot

    # ────────────────────────────────────────────────
    # Split host lists in globals
    # ────────────────────────────────────────────────
    def split_hosts(s: str) -> list[str]:
        if not s:
            return []
        return [h.strip() for h in s.split(',') if h.strip()]

    g = config['globals']
    g['FLUX_HOSTS']  = split_hosts(g.get('FLUX_HOST', ''))
    g['WAN_HOSTS']   = split_hosts(g.get('WAN_HOST',  ''))
    g['QWEN_HOSTS']  = split_hosts(g.get('QWEN_HOST', ''))
    g['QWEN_MODE']   = g.get('QWEN_MODE', '5angles')
    # Keep old HOST as ultimate fallback
    g['FALLBACK_HOST'] = g.get('HOST', '127.0.0.1:8188')

    # Debug print
    print("Global hosts parsed:")
    print(f"  FLUX_HOSTS   = {g['FLUX_HOSTS']}")
    print(f"  WAN_HOSTS    = {g['WAN_HOSTS']}")
    print(f"  QWEN_HOSTS   = {g['QWEN_HOSTS']}")
    print(f"  fallback     = {g['FALLBACK_HOST']}")

    return config