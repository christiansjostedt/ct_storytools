import json
import sys
import uuid
import time
import random
from io import StringIO
import os
try:
    import requests
except ImportError:
    requests = None

# Defaults for None inputs
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

class WorkflowTrigger:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_json": ("STRING", {"multiline": True, "default": ""}),
                "host": ("STRING", {"default": "127.0.0.1:8188"}),
                "width": ("INT", {"default": 960, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 720, "min": 64, "max": 4096}),
            },
            "optional": {
                "json_file": ("STRING", {"default": "", "multiline": False}),
                "num_jobs": ("INT", {"default": 1, "min": 1, "max": 50}),
                "project": ("STRING", {"default": "project", "multiline": False}),
                "sequence": ("STRING", {"default": "seq", "multiline": False}),
                "shot": ("STRING", {"default": "shot", "multiline": False}),
                "name": ("STRING", {"default": "name", "multiline": False}),
                "seed_start": ("INT", {"default": 0, "min": 0, "max": 2**32 - 1}),
            }
        }
    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("debug_output", "prompt_text", "return_output")
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = True

    def execute(self, workflow_json, host, width, height, json_file=None, num_jobs=1, project=None, sequence=None, shot=None, name=None, seed_start=0):
        debug_lines = []
        try:
            debug_lines.append("=== DEBUG START ===")
            if json_file is None or not json_file:
                json_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ct_storytools', 'workflows', 'ct_flux_t2i_base.json')
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
            width_updated = False
            height_updated = False
            prompt_dict = payload.get("prompt", {})
            if "21" in prompt_dict and "value" in prompt_dict["21"]["inputs"]:
                prompt_dict["21"]["inputs"]["value"] = width
                debug_lines.append(f" Updated WIDTH_SET (21): value={width}")
                width_updated = True
            if "22" in prompt_dict and "value" in prompt_dict["22"]["inputs"]:
                prompt_dict["22"]["inputs"]["value"] = height
                debug_lines.append(f" Updated HEIGHT_SET (22): value={height}")
                height_updated = True
            if not width_updated or not height_updated:
                debug_lines.append("⚠️ WIDTH_SET (21) or HEIGHT_SET (22) not found—ensure base workflow has these PrimitiveInt nodes")
            filename_prefix = None
            if all([project, sequence, shot, name]):
                filename_prefix = f"{project}/{sequence}/{shot}/{name}_"
                debug_lines.append(f"📁 Setting prefix: {filename_prefix}")
                output_dir = os.path.join(os.getenv('COMFYUI_OUTPUT', '/ComfyUI/output'), project, sequence, shot)
                os.makedirs(output_dir, exist_ok=True)
                debug_lines.append(f"✅ Created dir: {output_dir}")
            else:
                debug_lines.append("⚠️ Missing path fields; skipping dir/prefix")
            updated_count = 0
            for node_id, node in prompt_dict.items():
                if node.get("class_type") == "SaveImage":
                    node["inputs"]["filename_prefix"] = filename_prefix
                    updated_count += 1
                    debug_lines.append(f" Updated SaveImage {node_id}: {filename_prefix}")
            if updated_count == 0:
                debug_lines.append("⚠️ No SaveImage found—add one to base")
            base_payload = payload
            base_prompt = base_payload.get("prompt", base_payload)
            queued_ids = []
            for i in range(num_jobs):
                job_payload = json.loads(json.dumps(base_payload))
                job_prompt = job_payload.get("prompt", job_payload)
                seed = seed_start + i
                for node_id, node in job_prompt.items():
                    if node.get("class_type") == "KSampler":
                        node["inputs"]["seed"] = seed
                        debug_lines.append(f"🔀 Job {i+1}: Seed = {seed} (from SEED_START + {i})")
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
            debug_lines.append(f"✅ Queued {len(queued_ids)} jobs")
            if queued_ids:
                prompt_id = queued_ids[0]
                debug_lines.append(f"⏳ Polling first job {prompt_id[:8]} (10s)...")
                time.sleep(10)
                if requests is None:
                    debug_lines.append("❌ Cannot poll: requests library not available")
                else:
                    history_resp = requests.get(f"http://{host}/history/{prompt_id}")
                    if history_resp.ok:
                        history = history_resp.json().get(prompt_id, {})
                        debug_lines.append("=== FIRST JOB HISTORY ===")
                        debug_lines.append(json.dumps(history, indent=2)[:300] + "...")
                        outputs = history.get("outputs", {})
                        if outputs:
                            debug_lines.append(f"✅ {len(outputs)} outputs for job 1!")
                        else:
                            debug_lines.append("❌ No outputs for job 1—add SaveImage")
                        errors = history.get("errors", [])
                        if errors:
                            debug_lines.append(f"Errors: {errors}")
                    else:
                        debug_lines.append(f"⚠️ Poll failed: {history_resp.status_code}")
            debug_lines.append("=== DEBUG END ===")
            returned_json = json.dumps({'queued_ids': queued_ids})
            return ("\n".join(debug_lines), workflow_json, 1)
        except json.JSONDecodeError as e:
            debug_lines.append(f"❌ JSON Error (line {e.lineno}): {str(e)}")
            return ("\n".join(debug_lines), workflow_json, 0)
        except FileNotFoundError as e:
            return (str(e), workflow_json, 0)
        except Exception as e:
            import traceback
            debug_lines.append(f"❌ Error: {str(e)}")
            debug_lines.append(traceback.format_exc())
            return ("\n".join(debug_lines), workflow_json, 0)

# LOCAL MAPPINGS ONLY - No built-ins!
NODE_CLASS_MAPPINGS = {"WorkflowTrigger": WorkflowTrigger}
NODE_DISPLAY_NAME_MAPPINGS = {"WorkflowTrigger": "ct_flux_t2i"}