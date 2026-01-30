# fs_utils.py - Portable FS Utils Node for Dir Creation & Dummy Copy/Delete
import os
import shutil
import glob
import json
import requests  # For internal queuing
import time
import uuid
import random
from io import StringIO
import traceback
import sys

# Copied from ct_wan2_5s.py for node extraction and defaults
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

class CTServersideExecution:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["ct_wan2_5s", "LTX2_i2v", "LTX2_t2v"], {"default": "ct_wan2_5s"}),
                "project": ("STRING", {"default": "project", "multiline": False}),
                "sequence": ("STRING", {"default": "seq", "multiline": False}),
                "shot": ("STRING", {"default": "shot", "multiline": False}),
                "name": ("STRING", {"default": "name", "multiline": False}),
                "workflow": ("STRING", {"default": "workflow", "multiline": True}),  # Positive prompt
                "output_base": ("STRING", {"default": "/ComfyUI/output", "multiline": False}),
            },
            "optional": {
                "settings": ("STRING", {"default": "{}", "multiline": True}),
                "width": ("INT", {"default": 1920, "min": 64, "max": 4096}),
                "height": ("INT", {"default": 1080, "min": 64, "max": 4096}),
                "timestamp": ("INT", {"default": 0, "min": 0, "max": 9999999999}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("debug_output",)
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = False

    def execute(self, mode, project, sequence, shot, name, workflow, output_base, settings="{}", width=1920, height=1080, timestamp=0):
        debug_lines = [f"WAN Launcher Ts: {timestamp} | Prompt preview: {workflow[:100]}..."]
        queued_sub_ids = []
        local_host = "127.0.0.1:8188"
        base_wan_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'workflows', 'ct_wan2_5s_base.json')
        try:
            if mode != "ct_wan2_5s":
                raise ValueError(f"Unsupported mode: {mode}")
            shot_dir = os.path.join(output_base, project, sequence, shot)
            debug_lines.append(f"📁 Scanning: {shot_dir}")
            if not os.path.exists(shot_dir):
                debug_lines.append("⚠️ Shot dir missing—FLUX may not have run yet")
                return ("\n".join(debug_lines),)
            img_pattern = os.path.join(shot_dir, f"{name}__*.png")
            images = sorted(glob.glob(img_pattern))
            debug_lines.append(f"🔍 Found {len(images)} images: {[os.path.basename(p) for p in images[:3]]}...")  # First 3 for brevity
            if not images:
                return ("\n".join(debug_lines + ["⚠️ No images to process"]),)

            settings_dict = json.loads(settings) if settings else {}
            negative_prompt = settings_dict.get('NEGATIVE_PROMPT', '')  # From config if passed

            for img_path in images:
                basename = os.path.basename(img_path)
                vid_basename = basename.replace('.png', '.mp4')
                vid_path = os.path.join(shot_dir, vid_basename)
                if os.path.exists(vid_path):
                    debug_lines.append(f"⏭️ Skip existing: {vid_basename}")
                    continue
                debug_lines.append(f"🚀 WAN for: {basename}")

                # Build sub-payload (reuse ct_wan2_5s.py style)
                if not os.path.exists(base_wan_path):
                    raise FileNotFoundError(f"WAN base missing: {base_wan_path}")
                with open(base_wan_path, 'r') as f:
                    loaded_data = json.load(f)
                payload_str = json.dumps(loaded_data)
                # Replaces (like in ct_wan2_5s.py)
                payload_str = payload_str.replace("REPLACETEXT", workflow)
                payload_str = payload_str.replace("PROJECT", project).replace("SEQUENCE", sequence).replace("SHOT", shot).replace("NAME", name)
                sub_payload = json.loads(payload_str)
                sub_prompt = sub_payload.get("prompt", sub_payload)

                # Single-image overrides
                if "15" in sub_prompt:  # LoadImage
                    sub_prompt["15"]["inputs"]["image"] = basename  # Exact filename
                if "6" in sub_prompt:  # ImageResize+
                    sub_prompt["6"]["inputs"]["width"] = width
                    sub_prompt["6"]["inputs"]["height"] = height
                # SaveVideo prefix for match
                basename_noext = basename[:-4]  # Drop .png
                video_prefix = f"{project}/{sequence}/{shot}/{basename_noext}_"
                if "8" in sub_prompt:
                    sub_prompt["8"]["inputs"]["filename_prefix"] = video_prefix
                # Random seeds (like ct_wan2_5s.py)
                seed = random.randint(0, 2**32 - 1)
                for sampler_id in ["9:235", "9:236"]:
                    if sampler_id in sub_prompt:
                        sub_prompt[sampler_id]["inputs"]["noise_seed"] = seed
                # Negative if passed
                if negative_prompt and "11" in sub_prompt:  # CLIPTextEncode (negative)
                    sub_prompt["11"]["inputs"]["text"] = negative_prompt

                # Extract/wrap (reuse function)
                final_sub_payload = extract_prompt_from_workflow(sub_payload) if "nodes" in sub_payload else {"prompt": sub_prompt}
                final_sub_payload["client_id"] = str(uuid.uuid4())

                # Internal queue
                if requests is None:
                    debug_lines.append("❌ requests missing—cannot queue sub-job")
                    continue
                resp = requests.post(f"http://{local_host}/prompt", json=final_sub_payload)
                if resp.ok:
                    sub_id = resp.json().get("prompt_id")
                    queued_sub_ids.append(sub_id)
                    debug_lines.append(f"✅ Sub-ID: {sub_id[:8]} for {basename}")
                else:
                    debug_lines.append(f"❌ Sub-fail {basename}: {resp.text}")

            debug_lines.append(f"✅ Launcher done: {len(queued_sub_ids)} WAN sub-jobs queued")
            return ("\n".join(debug_lines),)
        except Exception as e:
            debug_lines.append(f"❌ Launcher Error: {str(e)}")
            debug_lines.append(traceback.format_exc())
            return ("\n".join(debug_lines),)

# LOCAL MAPPINGS ONLY - No built-ins!
NODE_CLASS_MAPPINGS = {"CTServersideExecution": CTServersideExecution}
NODE_DISPLAY_NAME_MAPPINGS = {"CTServersideExecution": "CT Serverside Execution"}