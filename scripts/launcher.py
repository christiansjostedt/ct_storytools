#!/usr/bin/env python3
# Portable Launcher via ComfyUI API - Parses config, builds/modifies workflow JSONs locally, queues remotely.
# No FS/exec/SSH—pure HTTP to remote server (e.g., 172.16.1.12:8188).
import json
import os
import time
import requests  # For API calls
import sys
from io import StringIO
import parser  # Your config parser (fixed import)

# Relative paths (local-only for loading bases)
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
WORKFLOWS_DIR = os.path.join(ROOT_DIR, 'workflows')

jobtype_to_json = {
    'ct_flux_t2i': os.path.join(WORKFLOWS_DIR, 'ct_flux_t2i_node.json'),  # Use the node wrapper
    'ct_wan2_5s': os.path.join(WORKFLOWS_DIR, 'ct_wan2_5s_node.json'),    # Use the node wrapper
    'ct_qwen_i2i': os.path.join(WORKFLOWS_DIR, 'ct_qwen_i2i_base.json'),
}

def load_and_modify_workflow(base_path: str, job_data: dict, seed_start: int = 0) -> dict:
    """Load base JSON, inject job params (prompt, dims, prefix, seeds). Returns ready payload."""
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"Base workflow missing: {base_path}")
    with open(base_path, 'r') as f:
        loaded_data = json.load(f)
    payload_str = json.dumps(loaded_data)
    # Cache-bust: Append unique ignored token to prompt (preserves reproducibility)
    cache_buster = f" [ts:{int(time.time()*1000)}]"
    job_data['workflow_json'] += cache_buster
    # Inject workflow_json (replace REPLACETEXT)
    payload_str = payload_str.replace("REPLACETEXT", job_data['workflow_json'])
    # Parse back to dict
    payload = json.loads(payload_str)
    if "nodes" in payload:
        prompt_dict = payload  # Full workflow mode
    else:
        prompt_dict = payload.get("prompt", payload)  # API-wrapped mode

    # Common params
    project = job_data['project']
    sequence = job_data['sequence']
    shot_id = job_data['shot_id']
    subshot_id = job_data['subshot_id']
    width = job_data['width']
    height = job_data['height']
    name = job_data['name']
    num_jobs = job_data['num_jobs']
    jt = job_data['jt']

    if 'flux' in jt.lower():
        # For ct_flux_t2i_node.json — override inputs of node "1" (WorkflowTrigger)
        flux_node = prompt_dict.get("1", {})
        if not flux_node or flux_node.get("class_type") != "WorkflowTrigger":
            raise ValueError("WorkflowTrigger node not found in ct_flux_t2i_node.json")
        inputs = flux_node.get("inputs", {})

        # Required inputs
        inputs["workflow_json"] = job_data['workflow_json']  # Already replaced, but ensure
        inputs["host"] = "127.0.0.1:8188"  # Local for internal queuing
        inputs["width"] = width
        inputs["height"] = height

        # Optional inputs
        inputs["json_file"] = ""  # Use default base
        inputs["num_jobs"] = num_jobs  # From FLUX_ITERATIONS
        inputs["project"] = project
        inputs["sequence"] = sequence
        inputs["shot"] = shot_id
        inputs["name"] = name
        inputs["seed_start"] = job_data['seed_start']  # FIXED: Safe, modded value from config

        # Save back
        prompt_dict["1"]["inputs"] = inputs
        print(f"✅ Injected Flux params into WorkflowTrigger node '1': "
              f"project={project}, num_jobs={num_jobs}, seed_start={job_data['seed_start']}")

    elif 'wan' in jt.lower():
        # For ct_wan2_5s_node.json — override inputs of node "1" (CT_WAN_TRIGGER)
        wan_node = prompt_dict.get("1", {})
        if not wan_node or wan_node.get("class_type") != "CT_WAN_TRIGGER":
            raise ValueError("CT_WAN_TRIGGER node not found in ct_wan2_5s_node.json")
        inputs = wan_node.get("inputs", {})

        # Required inputs
        inputs["workflow_json"] = job_data['workflow_json']
        inputs["host"] = "127.0.0.1:8188"
        inputs["width"] = width
        inputs["height"] = height

        # Optional inputs
        inputs["json_file"] = ""
        inputs["num_jobs"] = 1  # Meta-job; node handles internals
        inputs["project"] = project
        inputs["sequence"] = sequence
        inputs["shot"] = shot_id
        inputs["name"] = name

        prompt_dict["1"]["inputs"] = inputs
        print(f"✅ Injected WAN params into CT_WAN_TRIGGER node '1': project={project}, name={name}")

    else:
        # Generic fallback
        for nid, node in prompt_dict.items():
            if node.get("class_type") in ["PrimitiveInt", "Int"]:
                if "value" in node["inputs"]:
                    node["inputs"]["value"] = width if "width" in nid.lower() else height
            if node.get("class_type") == "KSampler":
                seed = job_data['seed_start']  # Use fixed/modded seed_start
                node["inputs"]["seed"] = seed

    # Filename prefix on SaveImage/SaveVideo (all jts)
    filename_prefix = f"{project}/{sequence}/{shot_id}/{name}_"
    for nid, node in prompt_dict.items():
        if node.get("class_type") in ["SaveImage", "SaveVideo"]:
            if "filename_prefix" in node["inputs"]:
                node["inputs"]["filename_prefix"] = filename_prefix

    # Wrap if needed (API expects {"prompt": ...})
    if "prompt" not in payload:
        payload = {"prompt": prompt_dict}

    return payload

def queue_workflow_via_api(server_url: str, payload: dict, num_jobs: int = 1) -> list:
    """POST payload to /prompt, poll /history for each (sequential). Returns list of prompt_ids."""
    queued_ids = []
    base_payload = payload
    for i in range(num_jobs):
        job_payload = json.loads(json.dumps(base_payload))
        job_payload["client_id"] = str(time.time()) + str(i)  # Simple unique ID
        response = requests.post(f"{server_url}/prompt", json=job_payload)
        if response.status_code != 200:
            raise RuntimeError(f"Queue failed (code {response.status_code}): {response.text}")
        prompt_id = response.json().get("prompt_id")
        queued_ids.append(prompt_id)
        print(f"✅ Queued job {i+1}/{num_jobs}: ID {prompt_id[:8]}")
        # Optional: Poll first job
        if i == 0:
            time.sleep(10)
            history_resp = requests.get(f"{server_url}/history/{prompt_id}")
            if history_resp.status_code == 200:
                history = history_resp.json().get(prompt_id, {})
                print(f"📊 First job status: {len(history.get('outputs', {}))} outputs")
            else:
                print(f"⚠️ Poll failed: {history_resp.status_code}")
    return queued_ids

def collect_jobs(config, allowed_jobtypes=None, target_project=None, target_sequence=None, target_shot=None):
    """Portable job collection (no FS). Returns list of job dicts."""
    globals_data = config['globals']
    project = target_project or globals_data.get('PROJECT', 'default')
    if project not in config:
        raise ValueError(f"Project '{project}' not found in config")
    sequences_to_run = [target_sequence] if target_sequence else list(config[project].keys())
    shot_jobtypes = {}
    for seq in sequences_to_run:
        if seq in config[project]:
            for shot_id in config[project][seq]:
                for subshot_id in config[project][seq][shot_id]:
                    shot_data = config[project][seq][shot_id][subshot_id]
                    jobtype_str = shot_data.get('JOBTYPE') or shot_data.get('IMAGE_JOBTYPE') or shot_data.get('VIDEO_JOBTYPE')
                    if jobtype_str:
                        jobtypes_list = [jt.strip() for jt in jobtype_str.split(',') if jt.strip()]
                        if allowed_jobtypes:
                            jobtypes_list = [jt for jt in jobtypes_list if jt in allowed_jobtypes]
                        if jobtypes_list:
                            shot_jobtypes[(seq, shot_id, subshot_id)] = jobtypes_list

    jobs = []
    known_jobtypes = ['ct_flux_t2i', 'ct_wan2_5s', 'ct_qwen_i2i']
    for jt in known_jobtypes:
        if allowed_jobtypes and jt not in allowed_jobtypes:
            continue
        for sequence in sorted(sequences_to_run):
            if sequence not in config[project]:
                continue
            shots_to_run = sorted(config[project][sequence].keys()) if not target_shot else [target_shot]
            for shot_id in shots_to_run:
                for subshot_id in sorted(config[project][sequence][shot_id]):
                    shot_key_tuple = (sequence, shot_id, subshot_id)
                    if shot_key_tuple in shot_jobtypes and jt in shot_jobtypes[shot_key_tuple]:
                        shot_data = config[project][sequence][shot_id][subshot_id]

                        # ────────────────────────────────────────────────
                        # IMPROVED PROMPT BUILDING + DEBUGGING + JSON ESCAPING
                        prompt_parts = []

                        if pos := shot_data.get('POSITIVE_PROMPT', '').strip():
                            prompt_parts.append(pos)

                        if env := shot_data.get('ENVIRONMENT_PROMPT', '').strip():
                            prompt_parts.append(env)

                        if style := globals_data.get('GRAPHICAL_STYLE', '').strip():
                            prompt_parts.append(style)

                        workflow_json = ", ".join(prompt_parts) if prompt_parts else ""
                        workflow_json = workflow_json.rstrip(', \t\n\r').strip()

                        # Debug print of the final raw prompt
                        job_id_str = f"{sequence}/{shot_id}/{subshot_id}"
                        if workflow_json:
                            preview = workflow_json[:100] + "..." if len(workflow_json) > 100 else workflow_json
                            print(f"  → Prompt for {job_id_str} ({jt}):")
                            print(f"    {preview}")
                        else:
                            print(f"  ⚠️  Empty prompt built for {job_id_str} ({jt})")

                        # CRITICAL: Escape the prompt so inner quotes don't break JSON
                        workflow_json_escaped = json.dumps(workflow_json)[1:-1]

                        # Show what will actually go into the JSON string
                        if workflow_json_escaped:
                            preview_esc = workflow_json_escaped[:80] + "..." if len(workflow_json_escaped) > 80 else workflow_json_escaped
                            print(f"  → Escaped version starts: {preview_esc}")
                        else:
                            print(f"  → Empty (escaped) prompt for {job_id_str}")
                        # ────────────────────────────────────────────────

                        width = int(shot_data.get('WIDTH', globals_data.get('WIDTH', 1024)))
                        height = int(shot_data.get('HEIGHT', globals_data.get('HEIGHT', 1024)))
                        name = subshot_id
                        if 'flux' in jt.lower():
                            num_jobs = int(shot_data.get('FLUX_ITERATIONS', globals_data.get('FLUX_ITERATIONS', 1)))
                        elif 'wan' in jt.lower():
                            num_jobs = 1  # Wrapper queues internally
                        elif 'qwen' in jt.lower():
                            num_jobs = int(shot_data.get('GENERATE_QWEN_ANGLES', globals_data.get('GENERATE_QWEN_ANGLES', 1)))
                        else:
                            num_jobs = int(shot_data.get('ITERATIONS', globals_data.get('ITERATIONS', 1)))
                        jobs.append({
                            'project': project,
                            'sequence': sequence,
                            'shot_id': shot_id,
                            'subshot_id': subshot_id,
                            'jt': jt,
                            'shot_data': shot_data,
                            'num_jobs': num_jobs,
                            'workflow_json': workflow_json_escaped,           # ← now properly escaped
                            'width': width,
                            'height': height,
                            'name': name,
                            'globals': globals_data,
                            'seed_start': int(globals_data.get('SEED_START', 0)) % 4294967296  # safe modulo
                        })

    # Debug print of collected jobs
    print("\n=== DEBUG: Collected Jobs ===")
    for idx, job in enumerate(jobs):
        print(f"Job {idx+1}: jt={job['jt']}, seq={job['sequence']}, shot={job['shot_id']}, "
              f"subshot={job['subshot_id']}, num_jobs={job['num_jobs']}, name={job['name']}, "
              f"seed_start={job['seed_start']}")
    print(f"Total jobs collected: {len(jobs)}\n")

    return jobs

def run_storytools_execution(config, allowed_jobtypes=None, target_project=None, target_sequence=None, target_shot=None):
    """Core: Collect jobs, build payloads, queue sequentially via API."""
    globals_data = config['globals']
    server_url = f"http://{globals_data.get('HOST', '127.0.0.1:8188')}"
    print(f"🌐 Queuing to remote: {server_url}")
    jobs = collect_jobs(config, allowed_jobtypes, target_project, target_sequence, target_shot)
    if not jobs:
        print("No jobs to queue.")
        return []
    all_results = []
    for job in jobs:
        try:
            base_path = jobtype_to_json.get(job['jt'])
            if not base_path:
                print(f"⚠️ Skipping {job['jt']}: No base workflow")
                continue
            payload = load_and_modify_workflow(base_path, job, seed_start=job['seed_start'])
            queued_ids = queue_workflow_via_api(server_url, payload, job['num_jobs'])
            all_results.append({
                'job': job,
                'prompt_ids': queued_ids,
                'success': len(queued_ids) > 0
            })
            print(f"✅ {job['jt']} {job['project']}/{job['sequence']}/{job['shot_id']}/{job['subshot_id']}: "
                  f"{len(queued_ids)} queued")
        except Exception as e:
            print(f"❌ Error queuing {job['jt']}: {e}")
            all_results.append({'job': job, 'success': False, 'error': str(e)})
    total_queued = sum(len(r['prompt_ids']) for r in all_results if r.get('success'))
    print(f"\n✅ Total queued: {total_queued} across {len(all_results)} jobs")
    return all_results

def run_all(config_path=None, allowed_jobtypes=None):
    """Entrypoint: Parse and run all."""
    if config_path is None:
        default_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'story_template.txt')
        if os.path.exists(default_path):
            config_path = default_path
        else:
            raise FileNotFoundError("No default config found.")
    config = parser.parse_config(config_path)
    project = config['globals']['PROJECT']
    print("Running all shots across all sequences...")
    full_results = run_storytools_execution(config=config, allowed_jobtypes=allowed_jobtypes, target_project=project)
    print(f"\n=== FINAL SUMMARY: {len(full_results)} executions "
          f"({sum(1 for r in full_results if r.get('success'))} successful) ===")
    for i, res in enumerate(full_results):
        status = "✅" if res.get('success') else "❌"
        print(f"{status} Execution {i+1}: {res.get('prompt_ids', [])} | Error: {res.get('error', 'None')}")
    return full_results

if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_all(config_path)