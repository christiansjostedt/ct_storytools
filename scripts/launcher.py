#!/usr/bin/env python3
# Portable Launcher via ComfyUI API
# Updated: support FLUX_HOSTS, WAN_HOSTS, QWEN_HOSTS → round-robin per job type
# Added: support for ct_qwen_cameratransform using real QwenCameraTrigger node
# Updated 2025/2026: LoRAs now passed via WorkflowTrigger inputs instead of patching base workflow

import json
import os
import time
import requests
import sys
from collections import deque
import parser  # config parser

# Relative paths
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
WORKFLOWS_DIR = os.path.join(ROOT_DIR, 'workflows')

jobtype_to_json = {
    'ct_flux_t2i': os.path.join(WORKFLOWS_DIR, 'ct_flux_t2i_node.json'),
    'ct_wan2_5s':  os.path.join(WORKFLOWS_DIR, 'ct_wan2_5s_node.json'),
    'ct_qwen_i2i': os.path.join(WORKFLOWS_DIR, 'ct_qwen_i2i_base.json'),
    'ct_qwen_cameratransform': os.path.join(WORKFLOWS_DIR, 'ct_qwen_cameratransform_node.json'),
}

# Round-robin queues per job family
flux_host_queue  = None
wan_host_queue   = None
qwen_host_queue  = None
fallback_host    = "http://127.0.0.1:8188"


def init_host_queues(globals_data):
    global flux_host_queue, wan_host_queue, qwen_host_queue, fallback_host

    flux_hosts = globals_data.get('FLUX_HOSTS', [])
    wan_hosts  = globals_data.get('WAN_HOSTS',  [])
    qwen_hosts = globals_data.get('QWEN_HOSTS', [])
    fallback   = globals_data.get('FALLBACK_HOST', '127.0.0.1:8188')

    flux_host_queue = deque([f"http://{h}" for h in flux_hosts]) if flux_hosts else None
    wan_host_queue  = deque([f"http://{h}" for h in wan_hosts])  if wan_hosts  else None
    qwen_host_queue = deque([f"http://{h}" for h in qwen_hosts]) if qwen_hosts else None
    fallback_host   = f"http://{fallback}"

    print("Host queues initialized:")
    print(f"  flux  → {flux_host_queue}")
    print(f"  wan   → {wan_host_queue}")
    print(f"  qwen  → {qwen_host_queue}")
    print(f"  fallback → {fallback_host}")


def get_next_host(jobtype: str) -> str:
    """Round-robin host selection per job family"""
    global flux_host_queue, wan_host_queue, qwen_host_queue, fallback_host

    jt_lower = jobtype.lower()

    if 'flux' in jt_lower and flux_host_queue and len(flux_host_queue) > 0:
        host = flux_host_queue.popleft()
        flux_host_queue.append(host)
        print(f"→ Using FLUX host: {host}")
        return host

    if 'wan' in jt_lower and wan_host_queue and len(wan_host_queue) > 0:
        host = wan_host_queue.popleft()
        wan_host_queue.append(host)
        print(f"→ Using WAN host: {host}")
        return host

    if 'qwen' in jt_lower or 'cameratransform' in jt_lower:
        if qwen_host_queue and len(qwen_host_queue) > 0:
            host = qwen_host_queue.popleft()
            qwen_host_queue.append(host)
            print(f"→ Using QWEN host: {host}")
            return host

    # fallback
    print(f"→ Using fallback host: {fallback_host}")
    return fallback_host


def load_and_modify_workflow(base_path: str, job_data: dict, seed_start: int = 0) -> tuple[dict, str]:
    if not os.path.exists(base_path):
        raise FileNotFoundError(f"Base workflow missing: {base_path}")

    with open(base_path, 'r') as f:
        loaded_data = json.load(f)

    payload_str = json.dumps(loaded_data)
    # Cache-bust
    cache_buster = f" [ts:{int(time.time()*1000)}]"
    job_data['workflow_json'] += cache_buster

    payload_str = payload_str.replace("REPLACETEXT", job_data['workflow_json'])
    payload = json.loads(payload_str)

    if "nodes" in payload:
        prompt_dict = payload
    else:
        prompt_dict = payload.get("prompt", payload)

    # Common fields
    project    = job_data['project']
    sequence   = job_data['sequence']
    shot_id    = job_data['shot_id']
    subshot_id = job_data['subshot_id']
    width      = job_data['width']
    height     = job_data['height']
    name       = job_data['name']
    num_jobs   = job_data['num_jobs']
    jt         = job_data['jt']

    server_url = get_next_host(jt)

    if 'flux' in jt.lower():
        flux_node = prompt_dict.get("1", {})
        if not flux_node or flux_node.get("class_type") != "WorkflowTrigger":
            raise ValueError("WorkflowTrigger node not found")

        inputs = flux_node.setdefault("inputs", {})
        inputs["workflow_json"] = job_data['workflow_json']
        inputs["host"]          = "127.0.0.1:8188"
        inputs["width"]         = width
        inputs["height"]        = height
        inputs["json_file"]     = ""
        inputs["num_jobs"]      = num_jobs
        inputs["project"]       = project
        inputs["sequence"]      = sequence
        inputs["shot"]          = shot_id
        inputs["name"]          = name
        inputs["seed_start"]    = job_data['seed_start']

        # ── Pass LoRAs to WorkflowTrigger ───────────────────────────────
        globals_d = job_data['globals']
        shot_d    = job_data['shot_data']

        def get_val(k, default=""):
            v = shot_d.get(k) or globals_d.get(k, default)
            return v.strip() if isinstance(v, str) else default

        for i in range(1, 9):
            fn_key   = f"FLUX_LORA{i}"
            str_key  = f"FLUX_LORA{i}_STRENGTH"
            filename = get_val(fn_key, "")
            strength = get_val(str_key, "1.0")

            inputs[f"lora_{i}"] = filename
            try:
                inputs[f"lora_{i}_strength"] = float(strength)
            except (ValueError, TypeError):
                inputs[f"lora_{i}_strength"] = 1.0

        # ── NEW DEBUG: Show exactly what LoRA values are being sent to the trigger node ──
        print("DEBUG: LoRA inputs sent to WorkflowTrigger node:")
        for k in sorted(inputs):
            if k.startswith("lora_"):
                print(f"  {k:12}: {inputs[k]!r}")

        prompt_dict["1"]["inputs"] = inputs

    elif 'wan' in jt.lower():
        wan_node = prompt_dict.get("1", {})
        if not wan_node or wan_node.get("class_type") != "CT_WAN_TRIGGER":
            raise ValueError("CT_WAN_TRIGGER node not found")

        inputs = wan_node.setdefault("inputs", {})
        inputs["workflow_json"] = job_data['workflow_json']
        inputs["host"]          = "127.0.0.1:8188"
        inputs["width"]         = width
        inputs["height"]        = height
        inputs["json_file"]     = ""
        inputs["num_jobs"]      = 1
        inputs["project"]       = project
        inputs["sequence"]      = sequence
        inputs["shot"]          = shot_id
        inputs["name"]          = name

        prompt_dict["1"]["inputs"] = inputs

    elif 'qwen_cameratransform' in jt.lower():
        trigger_node = prompt_dict.get("1", {})
        if not trigger_node or trigger_node.get("class_type") != "QwenCameraTrigger":
            raise ValueError("QwenCameraTrigger node (id=1) not found or wrong class_type")

        inputs = trigger_node.setdefault("inputs", {})

        inputs["mode"]       = job_data['shot_data'].get('QWEN_CAMERATRANSFORMATION_MODE',
                                                        job_data['globals'].get('QWEN_CAMERATRANSFORMATION_MODE', 'FrontBackLeftRight'))
        inputs["host"]       = "127.0.0.1:8188"
        inputs["input_dir"]  = "output"
        inputs["project"]    = project
        inputs["sequence"]   = sequence
        inputs["shot"]       = shot_id
        inputs["name"]       = name
        inputs["json_file"]  = ""
        inputs["seed_base"]  = job_data['seed_start']

        prompt_dict["1"]["inputs"] = inputs

    else:
        # generic fallback
        for nid, node in prompt_dict.items():
            cls = node.get("class_type", "")
            if cls in ["PrimitiveInt", "Int"] and "value" in node["inputs"]:
                if "width"  in nid.lower(): node["inputs"]["value"] = width
                if "height" in nid.lower(): node["inputs"]["value"] = height
            if cls == "KSampler":
                node["inputs"]["seed"] = job_data['seed_start']

    # Filename prefix (common)
    filename_prefix = f"{project}/{sequence}/{shot_id}/{name}_"
    for nid, node in prompt_dict.items():
        if node.get("class_type") in ["SaveImage", "SaveVideo"]:
            if "filename_prefix" in node["inputs"]:
                node["inputs"]["filename_prefix"] = filename_prefix

    if "prompt" not in payload:
        payload = {"prompt": prompt_dict}

    return payload, server_url


def queue_workflow_via_api(server_url: str, payload: dict, num_jobs: int = 1) -> list:
    queued_ids = []
    base_payload = payload

    for i in range(num_jobs):
        job_payload = json.loads(json.dumps(base_payload))
        job_payload["client_id"] = f"{time.time()}_{i}"

        try:
            resp = requests.post(f"{server_url}/prompt", json=job_payload, timeout=15)
            resp.raise_for_status()
            prompt_id = resp.json().get("prompt_id")
            queued_ids.append(prompt_id)
            print(f"Queued {i+1}/{num_jobs} → {server_url} | ID: {prompt_id[:8]}...")
        except Exception as e:
            print(f"Queue failed on {server_url}: {e}")

    return queued_ids


def collect_jobs(config, allowed_jobtypes=None, target_project=None, target_sequence=None, target_shot=None):
    globals_data = config['globals']
    project = target_project or globals_data.get('PROJECT', 'default')

    if project not in config:
        raise ValueError(f"Project '{project}' not found")

    sequences_to_run = [target_sequence] if target_sequence else list(config[project].keys())

    jobs = []

    known_jobtypes = ['ct_flux_t2i', 'ct_wan2_5s', 'ct_qwen_i2i', 'ct_qwen_cameratransform']

    for jt in known_jobtypes:
        if allowed_jobtypes and jt not in allowed_jobtypes:
            continue

        for seq in sorted(sequences_to_run):
            if seq not in config[project]:
                continue
            shots_to_run = sorted(config[project][seq].keys()) if not target_shot else [target_shot]

            for shot_id in shots_to_run:
                for subshot_id in sorted(config[project][seq][shot_id]):
                    shot_data = config[project][seq][shot_id][subshot_id]
                    jobtype_str = shot_data.get('JOBTYPE') or shot_data.get('IMAGE_JOBTYPE') or shot_data.get('VIDEO_JOBTYPE')

                    if not jobtype_str:
                        continue

                    jobtypes_list = [j.strip() for j in jobtype_str.split(',') if j.strip()]
                    if jt not in jobtypes_list:
                        continue

                    workflow_json = ""
                    if jt not in ['ct_qwen_cameratransform']:
                        prompt_parts = []
                        if pos := shot_data.get('POSITIVE_PROMPT', '').strip():
                            prompt_parts.append(pos)
                        if env := shot_data.get('ENVIRONMENT_PROMPT', '').strip():
                            prompt_parts.append(env)
                        if style := globals_data.get('GRAPHICAL_STYLE', '').strip():
                            prompt_parts.append(style)
                        workflow_json = ", ".join(prompt_parts).strip()

                    workflow_json_escaped = json.dumps(workflow_json)[1:-1] if workflow_json else ""

                    width  = int(shot_data.get('WIDTH',  globals_data.get('WIDTH',  1024)))
                    height = int(shot_data.get('HEIGHT', globals_data.get('HEIGHT', 1024)))
                    name   = subshot_id

                    if 'flux' in jt.lower():
                        num_jobs = int(shot_data.get('FLUX_ITERATIONS', globals_data.get('FLUX_ITERATIONS', 1)))
                    elif 'wan' in jt.lower():
                        num_jobs = 1
                    elif 'qwen' in jt.lower():
                        num_jobs = int(shot_data.get('GENERATE_QWEN_ANGLES', globals_data.get('GENERATE_QWEN_ANGLES', 1)))
                    else:
                        num_jobs = int(shot_data.get('ITERATIONS', globals_data.get('ITERATIONS', 1)))

                    jobs.append({
                        'project':     project,
                        'sequence':    seq,
                        'shot_id':     shot_id,
                        'subshot_id':  subshot_id,
                        'jt':          jt,
                        'shot_data':   shot_data,
                        'num_jobs':    num_jobs,
                        'workflow_json': workflow_json_escaped,
                        'width':       width,
                        'height':      height,
                        'name':        name,
                        'globals':     globals_data,
                        'seed_start':  int(globals_data.get('SEED_START', 0)) % 4294967296,
                    })

    print(f"Collected {len(jobs)} jobs")
    return jobs


def run_storytools_execution(config, allowed_jobtypes=None, target_project=None, target_sequence=None, target_shot=None):
    globals_data = config['globals']
    init_host_queues(globals_data)

    jobs = collect_jobs(config, allowed_jobtypes, target_project, target_sequence, target_shot)
    if not jobs:
        print("No jobs to queue.")
        return []

    all_results = []

    for job in jobs:
        try:
            base_path = jobtype_to_json.get(job['jt'])
            if not base_path:
                print(f"Skipping {job['jt']}: no base workflow")
                continue

            payload, target_server = load_and_modify_workflow(base_path, job, job['seed_start'])

            queued_ids = queue_workflow_via_api(
                server_url = target_server,
                payload    = payload,
                num_jobs   = job['num_jobs']
            )

            all_results.append({
                'job': job,
                'prompt_ids': queued_ids,
                'server': target_server,
                'success': len(queued_ids) > 0
            })

            print(f"{job['jt']} {job['project']}/{job['sequence']}/{job['shot_id']}/{job['subshot_id']} → "
                  f"{len(queued_ids)} jobs queued on {target_server}")

        except Exception as e:
            print(f"Error queuing {job['jt']}: {e}")
            all_results.append({
                'job': job,
                'success': False,
                'error': str(e)
            })

    total_queued = sum(len(r['prompt_ids']) for r in all_results if r.get('success'))
    print(f"Total queued: {total_queued} across {len(all_results)} job groups")
    return all_results


def run_all(config_path=None, allowed_jobtypes=None, only_sequence=None):
    if config_path is None:
        default = os.path.join(os.path.dirname(__file__), '..', 'configs', 'story_template.txt')
        config_path = default if os.path.exists(default) else None
        if not config_path:
            raise FileNotFoundError("No config path provided and no default found.")

    config = parser.parse_config(config_path)
    project = config['globals']['PROJECT']
    seq_info = f" (sequence: {only_sequence})" if only_sequence else ""
    print(f"Running all shots — project: {project}{seq_info}")

    full_results = run_storytools_execution(
        config=config,
        allowed_jobtypes=allowed_jobtypes,
        target_project=project,
        target_sequence=only_sequence,          # ← this is the key addition
    )

    print(f"\n=== SUMMARY: {len(full_results)} executions "
          f"({sum(1 for r in full_results if r.get('success'))} successful) ===")

    return full_results


if __name__ == "__main__":
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    run_all(config_path)