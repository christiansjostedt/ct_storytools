import json
import sys
import uuid
import time
import random
from io import StringIO
import os
import re  # For frame extraction
import glob  # NEW: For flexible video pattern matching
try:
    import requests
except ImportError:
    requests = None

LOADIMAGE_DIR = os.getenv('COMFYUI_OUTPUT', '/ComfyUI/output')
NODE_DEFAULTS = {
    "KSampler": {"steps": 20, "cfg": 8.0, "sampler_name": "euler", "scheduler": "normal", "denoise": 1.0, "seed": 0},
    "FluxGuidance": {"guidance": 3.5},
    "CLIPTextEncodeFlux": {"guidance": 3.5},
}

def extract_prompt_from_workflow(full_workflow):
    nodes = full_workflow.get('nodes', [])
    links = full_workflow.get('links', [])
    node_data = {}
    for node in nodes:
        node_id = str(node['id'])
        class_type = node['type']
        inputs = {}
        input_defs = node.get('inputs', [])
        widget_values = node.get('widgets_values', [])
        for i, input_def in enumerate(input_defs):
            input_name = input_def['name']
            if i < len(widget_values):
                value = widget_values[i]
                inputs[input_name] = value
                print(f" Mapped {input_name} = {value} (index {i})", file=sys.stderr)
            else:
                inputs[input_name] = None
        for link in links:
            if len(link) >= 5:
                link_id, from_node, from_slot, to_node, to_slot = link[:5]
                to_node_str = str(to_node)
                if to_node_str == node_id and to_slot < len(input_defs):
                    input_name = input_defs[to_slot]['name']
                    inputs[input_name] = [str(from_node), int(from_slot)]
                    print(f" Linked {input_name} = [{from_node}, {from_slot}]", file=sys.stderr)
        if class_type in NODE_DEFAULTS:
            defaults = NODE_DEFAULTS[class_type]
            for key, val in defaults.items():
                if inputs.get(key) is None:
                    inputs[key] = val
                    print(f" Defaulted {key} = {val}", file=sys.stderr)
        node_data[node_id] = {
            "class_type": class_type,
            "inputs": inputs
        }
    api_prompt = {"prompt": node_data}
    return api_prompt

class CT_WAN_TRIGGER:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_json": ("STRING", {"multiline": True, "default": ""}),
                "host": ("STRING", {"default": "127.0.0.1:8188"}),
                "width": ("INT", {"default": 1280, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 720, "min": 64, "max": 4096}),
            },
            "optional": {
                "json_file": ("STRING", {"default": "", "multiline": False}),
                "num_jobs": ("INT", {"default": 1, "min": 1, "max": 50}),
                "project": ("STRING", {"default": "project", "multiline": False}),
                "sequence": ("STRING", {"default": "seq", "multiline": False}),
                "shot": ("STRING", {"default": "shot", "multiline": False}),
                "name": ("STRING", {"default": "name", "multiline": False}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("debug_output", "returned_json", "return_output")
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = True

    def execute(self, workflow_json, host, width, height, json_file=None, num_jobs=1, project=None, sequence=None, shot=None, name=None):
        debug_lines = []
        returned_json = None
        try:
            debug_lines.append("=== DEBUG START ===")
            debug_lines.append(f"📁 Output: {LOADIMAGE_DIR} | LoadImage: {LOADIMAGE_DIR}")
            if json_file is None or not json_file:
                json_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ct_storytools', 'workflows', 'ct_wan2_5s_base.json')
            base_path = json_file
            debug_lines.append(f"Using file: {base_path}")
            if not os.path.exists(base_path):
                raise FileNotFoundError(f"❌ File missing: {base_path}")
            with open(base_path, 'r') as f:
                loaded_data = json.load(f)
            payload_str = json.dumps(loaded_data)
            debug_lines.append(f"✅ Loaded ({len(payload_str)} chars): {payload_str[:300]}...")
            original_count = payload_str.count("REPLACETEXT")
            debug_lines.append(f"Found {original_count} 'REPLACETEXT'")
            if workflow_json.strip():
                payload_str = payload_str.replace("REPLACETEXT", workflow_json)
                debug_lines.append(f"✅ Replaced with '{workflow_json}'")
            else:
                debug_lines.append("⚠️ No text; using original")
            loaded_data = json.loads(payload_str)
            if "nodes" in loaded_data:
                debug_lines.append("🔄 Extracting from full workflow")
                payload = extract_prompt_from_workflow(loaded_data)
            else:
                if "prompt" not in loaded_data:
                    debug_lines.append("🔄 Wrapping API nodes in 'prompt'")
                    payload = {"prompt": loaded_data}
                else:
                    payload = loaded_data
            resize_updated = False
            for node_id, node in payload.get("prompt", {}).items():
                if node.get("class_type") == "ImageResize+":
                    node["inputs"]["width"] = width
                    node["inputs"]["height"] = height
                    debug_lines.append(f" Updated ImageResize+ {node_id}: width={width}, height={height}")
                    resize_updated = True
                    break
            if not resize_updated:
                debug_lines.append("⚠️ No ImageResize+ found—add one to base with width/height")
            base_payload = payload
            base_prompt = base_payload.get("prompt", base_payload)
            queued_ids = []
            if all([project, sequence, shot, name]):
                input_dir = os.path.join(LOADIMAGE_DIR, project, sequence, shot)
                debug_lines.append(f"📁 Scanning: {input_dir}")
                if not os.path.exists(input_dir):
                    debug_lines.append(f"⚠️ Dir missing (expected from flux): {input_dir} - queuing batch anyway")
                else:
                    image_extensions = ('.png', '.jpg', '.jpeg', '.bmp', '.tiff')
                    all_images = [f for f in os.listdir(input_dir) if f.lower().endswith(image_extensions) and f.startswith(name + "__")]
                    debug_lines.append(f"Found {len(all_images)} potential images: {all_images[:3]}{'...' if len(all_images) > 3 else ''}")
                    images_to_process = []
                    for image in all_images:
                        # Extract frame number from image name, e.g., "name__00001_.png" -> frame="00001"
                        match = re.match(rf'^{re.escape(name)}__(\d+)_?\.', image.lower(), re.IGNORECASE)
                        if not match:
                            debug_lines.append(f"⚠️ Skipping {image} - doesn't match expected pattern {name}__NNNNN_.")
                            continue
                        frame = match.group(1)
                        # ADAPTED: Flexible check for any video matching "name__{frame}__*.mp4" (handles buggy suffixes like __00001_)
                        video_pattern = os.path.join(input_dir, f"{name}__{frame}__*.mp4")
                        matching_videos = glob.glob(video_pattern)
                        if matching_videos:
                            first_video = matching_videos[0]
                            debug_lines.append(f"⏭️ Skipping {image} - video already exists: {os.path.basename(first_video)} (found {len(matching_videos)})")
                        else:
                            images_to_process.append(image)
                            debug_lines.append(f"✅ Processing {image} - no matching video found (pattern: {name}__{frame}__*.mp4)")
                    if not images_to_process:
                        debug_lines.append("⚠️ No new images to process (all have videos) - queuing batch workflow to scan later")
                        # Queue batch when no new images
                        job_payload = json.loads(json.dumps(base_payload))
                        job_prompt = job_payload.get("prompt", job_payload)
                        container_dir = f"{LOADIMAGE_DIR}/{project}/{sequence}/{shot}"
                        if "15" in job_prompt:
                            job_prompt["15"]["inputs"]["dir_path"] = container_dir
                            job_prompt["15"]["inputs"]["pattern"] = f"{name}__"
                            debug_lines.append(f" Set batch dir '15' to: {container_dir} (pattern: {name}__*)")
                        if "16" in job_prompt:
                            job_prompt["16"]["inputs"]["width"] = width
                            job_prompt["16"]["inputs"]["height"] = height
                        seed = random.randint(0, 2**32 - 1)
                        for sampler_id in ["9:235", "9:236"]:
                            if sampler_id in job_prompt:
                                job_prompt[sampler_id]["inputs"]["noise_seed"] = seed
                                debug_lines.append(f"🔀 Batch job seed: {seed} for {sampler_id}")
                        job_payload["client_id"] = str(uuid.uuid4())
                        if requests is None:
                            debug_lines.append("❌ Batch failed: requests library not available")
                        else:
                            response = requests.post(f"http://{host}/prompt", json=job_payload)
                            debug_lines.append(f"Batch status {response.status_code} | ID {job_payload['client_id'][:8]}")
                            if response.ok:
                                resp_data = response.json()
                                queued_ids = [resp_data.get("prompt_id")]
                                debug_lines.append("✅ Queued batch wan to scan/generate videos later")
                            else:
                                debug_lines.append(f"❌ Batch failed: {response.text}")
                        returned_json = json.dumps({'queued_ids': queued_ids})
                        debug_lines.append(f"✅ Queued {len(queued_ids)} batch jobs")
                    else:
                        debug_lines.append(f"Will process {len(images_to_process)} new images")
                        output_dir = input_dir
                        os.makedirs(output_dir, exist_ok=True)
                        debug_lines.append(f"✅ Using output dir: {output_dir}")
                        for i, image in enumerate(images_to_process):
                            job_payload = json.loads(json.dumps(base_payload))
                            job_prompt = job_payload.get("prompt", job_payload)
                            container_image_path = os.path.join(LOADIMAGE_DIR, project, sequence, shot, image)
                            if "15" in job_prompt:
                                job_prompt["15"]["inputs"]["image"] = container_image_path
                                debug_lines.append(f" Set LoadImage '15' to container path: {container_image_path}")
                            basename = os.path.splitext(image)[0]
                            video_prefix = f"{project}/{sequence}/{shot}/{basename}"
                            if "8" in job_prompt:
                                job_prompt["8"]["inputs"]["filename_prefix"] = video_prefix
                                debug_lines.append(f" Set SaveVideo prefix '8' to: {video_prefix}")
                            seed = random.randint(0, 2**32 - 1)
                            seed_set = False
                            for sampler_id in ["9:235", "9:236"]:
                                if sampler_id in job_prompt:
                                    job_prompt[sampler_id]["inputs"]["noise_seed"] = seed
                                    debug_lines.append(f"🔀 Job {i+1} ({image}): Seed {seed} for {sampler_id}")
                                    seed_set = True
                            if not seed_set:
                                debug_lines.append("⚠️ No KSamplerAdvanced samplers found—seeds unchanged")
                            job_payload["client_id"] = str(uuid.uuid4())
                            if requests is None:
                                debug_lines.append(f"❌ Job {i+1} ({image}) failed: requests library not available")
                                continue
                            response = requests.post(f"http://{host}/prompt", json=job_payload)
                            debug_lines.append(f"Job {i+1} ({image}): Status {response.status_code} | ID {job_payload['client_id'][:8]}")
                            if response.ok:
                                resp_data = response.json()
                                queued_ids.append(resp_data.get("prompt_id"))
                            else:
                                debug_lines.append(f"Job {i+1} ({image}) failed: {response.text}")
                        returned_json = json.dumps({'queued_ids': queued_ids})
                        debug_lines.append(f"✅ Queued {len(queued_ids)} batch jobs")
            else:
                debug_lines.append("⚠️ Missing path fields; using fallback num_jobs mode")
                for i in range(num_jobs):
                    job_payload = json.loads(json.dumps(base_payload))
                    job_prompt = job_payload.get("prompt", job_payload)
                    seed = random.randint(0, 2**32 - 1)
                    for sampler_id in ["9:235", "9:236"]:
                        if sampler_id in job_prompt:
                            job_prompt[sampler_id]["inputs"]["noise_seed"] = seed
                            debug_lines.append(f"🔀 Job {i+1}: Seed {seed} for {sampler_id}")
                            break
                    job_payload["client_id"] = str(uuid.uuid4())
                    if requests is None:
                        debug_lines.append(f"❌ Job {i+1} failed: requests library not available")
                        continue
                    response = requests.post(f"http://{host}/prompt", json=job_payload)
                    debug_lines.append(f"Job {i+1}: Status {response.status_code} | ID {job_payload['client_id'][:8]}")
                    if response.ok:
                        resp_data = response.json()
                        queued_ids.append(resp_data.get("prompt_id"))
                    else:
                        debug_lines.append(f"Job {i+1} failed: {response.text}")
                returned_json = json.dumps({'queued_ids': queued_ids})
                debug_lines.append(f"✅ Queued {len(queued_ids)} fallback jobs")
            if queued_ids:
                prompt_id = queued_ids[0]
                debug_lines.append(f"⏳ Polling first job {prompt_id[:8]} (up to 300s)...")
                poll_interval = 10  # seconds
                timeout = 300  # 5 minutes max
                start_time = time.time()
                job_complete = False
                while time.time() - start_time < timeout:
                    if requests is None:
                        debug_lines.append("❌ Cannot poll: requests library not available")
                        break
                    history_resp = requests.get(f"http://{host}/history/{prompt_id}")
                    if history_resp.ok:
                        full_history = history_resp.json()
                        history = full_history.get(prompt_id, {})
                        if history and 'outputs' in history and history['outputs']:
                            debug_lines.append("=== FIRST JOB HISTORY ===")
                            debug_lines.append(json.dumps(history, indent=2)[:300] + "...")
                            outputs = history.get("outputs", {})
                            debug_lines.append(f"✅ {len(outputs)} outputs for job 1!")
                            errors = history.get("errors", [])
                            if errors:
                                debug_lines.append(f"Errors: {errors}")
                            job_complete = True
                            break
                        else:
                            debug_lines.append(f"⏳ Job still running... (checked at {int(time.time() - start_time)}s)")
                    else:
                        debug_lines.append(f"⚠️ Poll failed: {history_resp.status_code}")
                    time.sleep(poll_interval)
                if not job_complete:
                    debug_lines.append("⚠️ Job timed out after 300s - still running or issue with workflow (check SaveVideo node)")
                else:
                    debug_lines.append("✅ First job completed successfully")
            debug_lines.append("=== DEBUG END ===")
            return ("\n".join(debug_lines), returned_json, 1)
        except json.JSONDecodeError as e:
            debug_lines.append(f"❌ JSON Error (line {e.lineno}): {str(e)}")
            return ("\n".join(debug_lines), None, 0)
        except FileNotFoundError as e:
            return (str(e), None, 0)
        except Exception as e:
            import traceback
            debug_lines.append(f"❌ Error: {str(e)}")
            debug_lines.append(traceback.format_exc())
            return ("\n".join(debug_lines), None, 0)

# LOCAL MAPPINGS ONLY - No built-ins!
NODE_CLASS_MAPPINGS = {"CT_WAN_TRIGGER": CT_WAN_TRIGGER}
NODE_DISPLAY_NAME_MAPPINGS = {"CT_WAN_TRIGGER": "ct_wan2_5s"}