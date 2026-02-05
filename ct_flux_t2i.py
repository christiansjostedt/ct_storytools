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

# Defaults for some nodes (you can expand this later)
NODE_DEFAULTS = {
    "KSampler": {"steps": 20, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0, "seed": 0},
    "FluxGuidance": {"guidance": 3.5},
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
                inputs[input_name] = widget_values[i]
            else:
                inputs[input_name] = None
        for link in links:
            if len(link) >= 5:
                _, from_node, from_slot, to_node, to_slot = link[:5]
                if str(to_node) == node_id and to_slot < len(input_defs):
                    input_name = input_defs[to_slot]['name']
                    inputs[input_name] = [str(from_node), int(from_slot)]
        if class_type in NODE_DEFAULTS:
            for key, val in NODE_DEFAULTS[class_type].items():
                if inputs.get(key) is None:
                    inputs[key] = val
        node_data[node_id] = {"class_type": class_type, "inputs": inputs}
    return {"prompt": node_data}


class WorkflowTrigger:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "workflow_json": ("STRING", {"multiline": True, "default": ""}),
                "host": ("STRING", {"default": "127.0.0.1:8188"}),
                "width": ("INT", {"default": 1024, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 1024, "min": 64, "max": 4096}),
            },
            "optional": {
                "json_file": ("STRING", {"default": ""}),
                "num_jobs": ("INT", {"default": 1, "min": 1, "max": 50}),
                "project": ("STRING", {"default": "project"}),
                "sequence": ("STRING", {"default": "seq"}),
                "shot": ("STRING", {"default": "shot"}),
                "name": ("STRING", {"default": "name"}),
                "seed_start": ("INT", {"default": 0, "min": 0, "max": 4294967295}),

                "lora_1": ("STRING", {"default": ""}),
                "lora_1_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_2": ("STRING", {"default": ""}),
                "lora_2_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_3": ("STRING", {"default": ""}),
                "lora_3_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_4": ("STRING", {"default": ""}),
                "lora_4_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_5": ("STRING", {"default": ""}),
                "lora_5_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_6": ("STRING", {"default": ""}),
                "lora_6_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_7": ("STRING", {"default": ""}),
                "lora_7_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
                "lora_8": ("STRING", {"default": ""}),
                "lora_8_strength": ("FLOAT", {"default": 1.0, "min": -10.0, "max": 10.0, "step": 0.05}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("debug_output", "prompt_text", "return_output")
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = True

    def execute(self, workflow_json, host, width, height,
                json_file="", num_jobs=1,
                project="project", sequence="seq", shot="shot", name="name",
                seed_start=0,
                lora_1="", lora_1_strength=1.0,
                lora_2="", lora_2_strength=1.0,
                lora_3="", lora_3_strength=1.0,
                lora_4="", lora_4_strength=1.0,
                lora_5="", lora_5_strength=1.0,
                lora_6="", lora_6_strength=1.0,
                lora_7="", lora_7_strength=1.0,
                lora_8="", lora_8_strength=1.0):

        debug_lines = ["=== WorkflowTrigger DEBUG START ==="]
        print("=== WorkflowTrigger START ===")

        try:
            # 1. Base workflow path - FIXED
            if not json_file:
                json_file = os.path.join(os.path.dirname(__file__), 'workflows', 'ct_flux_t2i_base.json')
            debug_lines.append(f"Resolved base path: {json_file}")
            print(f"Resolved base path: {json_file}")

            if not os.path.exists(json_file):
                debug_lines.append(f"ERROR: Base file does NOT exist at {json_file}")
                raise FileNotFoundError(f"Missing base workflow: {json_file}")
            debug_lines.append("Base file exists ✓")
            print("Base file exists ✓")

            # 2. Load raw json
            with open(json_file, 'r') as f:
                loaded_data = json.load(f)
            debug_lines.append(f"Loaded base JSON - {len(loaded_data)} top-level keys")
            print(f"Loaded base JSON - {len(loaded_data)} top-level keys")

            payload_str = json.dumps(loaded_data)
            debug_lines.append(f"Serialized length: {len(payload_str):,} chars")

            # 3. REPLACETEXT replacement
            original_count = payload_str.count("REPLACETEXT")
            debug_lines.append(f"Found {original_count} × REPLACETEXT")
            print(f"Found {original_count} × REPLACETEXT")

            replaced_count = 0
            if workflow_json.strip():
                payload_str = payload_str.replace("REPLACETEXT", workflow_json)
                replaced_count = original_count
                debug_lines.append(f"Replaced {replaced_count} placeholders")
                print(f"Replaced {replaced_count} placeholders")
            else:
                debug_lines.append("workflow_json empty → no replacement")

            # 4. Parse back to dict
            payload = json.loads(payload_str)
            debug_lines.append("Successfully parsed modified payload")

            # 5. Get prompt_dict
            if "prompt" in payload:
                prompt_dict = payload["prompt"]
                debug_lines.append("Using payload['prompt'] as prompt_dict")
            else:
                prompt_dict = payload
                debug_lines.append("Using top-level payload as prompt_dict")
            print(f"prompt_dict has {len(prompt_dict)} nodes")
            debug_lines.append(f"prompt_dict has {len(prompt_dict)} nodes")

            # 6. Basic structure check
            debug_lines.append(f"Has node 4 (UNET)? {'4' in prompt_dict}")
            debug_lines.append(f"Has node 13 (KSampler)? {'13' in prompt_dict}")
            debug_lines.append(f"Has node 14 (CLIPTextEncodeFlux)? {'14' in prompt_dict}")
            debug_lines.append(f"Has node 21 (width primitive)? {'21' in prompt_dict}")
            debug_lines.append(f"Has node 22 (height primitive)? {'22' in prompt_dict}")

            # 7. Conditioning check
            if '14' in prompt_dict:
                inputs14 = prompt_dict['14'].get('inputs', {})
                clip_l = inputs14.get('clip_l', 'MISSING')
                t5xxl = inputs14.get('t5xxl', 'MISSING')
                debug_lines.append(f"Node 14 clip_l: {clip_l[:80]}...")
                debug_lines.append(f"Node 14 t5xxl: {t5xxl[:80]}...")
                print(f"Node 14 clip_l starts: {clip_l[:80]}...")
                print(f"Node 14 t5xxl starts: {t5xxl[:80]}...")

            # 8. Apply width/height/filename
            filename_prefix = f"{project}/{sequence}/{shot}/{name}_" if all([project, sequence, shot, name]) else "ComfyUI"
            debug_lines.append(f"Setting filename_prefix: {filename_prefix}")

            save_nodes_updated = 0
            for nid, node in prompt_dict.items():
                if node.get("class_type") in ["SaveImage", "SaveVideo"]:
                    if "filename_prefix" in node["inputs"]:
                        node["inputs"]["filename_prefix"] = filename_prefix
                        save_nodes_updated += 1
            debug_lines.append(f"Updated {save_nodes_updated} SaveImage/SaveVideo nodes")

            if "21" in prompt_dict and "value" in prompt_dict["21"].get("inputs", {}):
                prompt_dict["21"]["inputs"]["value"] = width
                debug_lines.append(f"Set width primitive (21): {width}")
            if "22" in prompt_dict and "value" in prompt_dict["22"].get("inputs", {}):
                prompt_dict["22"]["inputs"]["value"] = height
                debug_lines.append(f"Set height primitive (22): {height}")

            # 9. LoRA application with debug
            loras = [
                (1, lora_1, lora_1_strength),
                (2, lora_2, lora_2_strength),
                (3, lora_3, lora_3_strength),
                (4, lora_4, lora_4_strength),
                (5, lora_5, lora_5_strength),
                (6, lora_6, lora_6_strength),
                (7, lora_7, lora_7_strength),
                (8, lora_8, lora_8_strength),
            ]
            applied_loras = 0
            for idx, filename, strength in loras:
                filename = filename.strip()
                if not filename:
                    debug_lines.append(f"LoRA {idx:2d} → skipped (empty)")
                    continue
                applied_loras += 1
                debug_lines.append(f"Applying LoRA {idx:2d}: '{filename}' @ {strength}")

                stack_node = "54" if idx <= 4 else "55"
                slot = ((idx - 1) % 4) + 1

                node = prompt_dict.get(stack_node)
                if not node or node.get("class_type") != "Lora Loader Stack (rgthree)":
                    debug_lines.append(f"LoRA {idx} → warning: node {stack_node} missing/wrong type")
                    continue

                inputs = node.setdefault("inputs", {})

                lora_key = f"lora_{slot:02d}"
                str_key  = f"strength_{slot:02d}"

                old_lora = inputs.get(lora_key, "<unset>")
                inputs[lora_key] = filename
                debug_lines.append(f"  → {stack_node}.{lora_key} = '{filename}' (was {old_lora})")

                old_strength = inputs.get(str_key, "<unset>")
                inputs[str_key] = float(strength)
                debug_lines.append(f"  → {stack_node}.{str_key} = {strength} (was {old_strength})")

            debug_lines.append(f"Applied {applied_loras} LoRAs")

            # 10. Before queuing
            debug_lines.append(f"About to queue {num_jobs} jobs (seed_start={seed_start})")
            print(f"About to queue {num_jobs} jobs")

            # Queuing loop
            queued_ids = []
            base_payload = {"prompt": prompt_dict}

            for i in range(num_jobs):
                job_payload = json.loads(json.dumps(base_payload))
                job_prompt = job_payload["prompt"]

                for nid, node in job_prompt.items():
                    if node.get("class_type") == "KSampler":
                        node["inputs"]["seed"] = (seed_start + i) % 4294967296
                        debug_lines.append(f"Job {i+1}: seed set to {(seed_start + i) % 4294967296}")
                        break

                job_payload["client_id"] = str(uuid.uuid4())

                if not requests:
                    debug_lines.append(f"Job {i+1} failed: requests not available")
                    continue

                try:
                    resp = requests.post(f"http://{host}/prompt", json=job_payload, timeout=30)
                    if resp.ok:
                        data = resp.json()
                        pid = data.get("prompt_id")
                        queued_ids.append(pid)
                        debug_lines.append(f"Queued job {i+1}/{num_jobs} → ID {pid[:8]}...")
                    else:
                        debug_lines.append(f"Queue failed job {i+1}: {resp.status_code} {resp.text[:200]}")
                except Exception as req_err:
                    debug_lines.append(f"Request error job {i+1}: {str(req_err)}")

            debug_lines.append(f"Queued total: {len(queued_ids)} jobs")
            debug_lines.append("=== WorkflowTrigger DEBUG END ===")
            print("=== WorkflowTrigger END ===")

            return ("\n".join(debug_lines), workflow_json, len(queued_ids))

        except Exception as e:
            import traceback
            debug_lines.append("CRITICAL EXCEPTION:")
            debug_lines.append(str(e))
            debug_lines.append(traceback.format_exc())
            print("CRITICAL EXCEPTION in WorkflowTrigger:")
            print(str(e))
            print(traceback.format_exc())
            return ("\n".join(debug_lines), workflow_json, 0)


# Mappings
NODE_CLASS_MAPPINGS = {"WorkflowTrigger": WorkflowTrigger}
NODE_DISPLAY_NAME_MAPPINGS = {"WorkflowTrigger": "ct_flux_t2i"}