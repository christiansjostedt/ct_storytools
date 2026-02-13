import json
import sys
import uuid
import time
import random
import os
import re
import glob
try:
    import requests
except ImportError:
    requests = None

LOADIMAGE_DIR = os.getenv('COMFYUI_OUTPUT', '/ComfyUI/output')

class CT_LTX2_i2v_trigger:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "input_prompt": ("STRING", {"multiline": True, "default": ""}),
                "host": ("STRING", {"default": "127.0.0.1:8188"}),
                "width": ("INT", {"default": 1280, "min": 64, "max": 4096, "step": 32}),
                "height": ("INT", {"default": 544, "min": 64, "max": 4096, "step": 32}),
                "video_length": ("INT", {"default": 361, "min": 9, "max": 1000, "step": 1,
                                        "tooltip": "Number of output frames. Must satisfy (length-1) divisible by 8."}),
                "checkpoint_name": ("STRING", {"default": "ltx-2-19b-distilled-fp8.safetensors"}),
                "fps": ("FLOAT", {"default": 24.0, "min": 1.0, "max": 60.0, "step": 0.5}),
            },
            "optional": {
                "json_file": ("STRING", {"default": "", "multiline": False}),
                "project": ("STRING", {"default": "project", "multiline": False}),
                "sequence": ("STRING", {"default": "seq", "multiline": False}),
                "shot": ("STRING", {"default": "shot", "multiline": False}),
                "name": ("STRING", {"default": "name", "multiline": False}),
                "regenerate": ("BOOLEAN", {"default": False, "label_on": "yes", "label_off": "no"}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("debug_output", "returned_json", "return_output")
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = True

    def execute(self, input_prompt, host,
                width, height, video_length, checkpoint_name, fps,
                json_file=None,
                project=None, sequence=None, shot=None, name=None,
                regenerate=False):

        debug_lines = []
        returned_json = None

        try:
            debug_lines.append("=== LTX 2.0 i2v Trigger START ===")
            debug_lines.append(f"Output base: {LOADIMAGE_DIR}")
            debug_lines.append(f"Regenerate mode: {'ON' if regenerate else 'OFF'}")

            # Adjust resolution to multiple of 32
            orig_w, orig_h = width, height
            width = max(64, round(width / 32) * 32)
            height = max(64, round(height / 32) * 32)
            if width != orig_w or height != orig_h:
                debug_lines.append(f"Resolution adjusted → {width}x{height} (÷32)")

            # Adjust video length to valid (n-1) % 8 == 0
            orig_len = video_length
            remainder = (video_length - 1) % 8
            if remainder != 0:
                video_length = video_length - remainder if (remainder <= 4) else video_length + (8 - remainder)
                video_length = max(9, video_length)
                debug_lines.append(f"Video length adjusted: {orig_len} → {video_length}")

            # Load base workflow
            if not json_file or not json_file.strip():
                # Default path: inside ct_storytools/workflows/
                base_dir = os.path.dirname(__file__)  # /ComfyUI/custom_nodes/ct_storytools
                json_file = os.path.join(base_dir, 'workflows', 'ct_ltx2_i2v_base.json')

            debug_lines.append(f"Loading base: {json_file}")

            if not os.path.exists(json_file):
                debug_lines.append("⚠️ Base workflow file not found!")
                raise FileNotFoundError(f"Base workflow missing: {json_file}")

            with open(json_file, 'r') as f:
                loaded_data = json.load(f)

            payload_str = json.dumps(loaded_data)

            if input_prompt.strip():
                payload_str = payload_str.replace("REPLACETEXT", input_prompt.strip())
                debug_lines.append("Prompt (REPLACETEXT) replaced")
            else:
                debug_lines.append("No prompt provided → using base prompt")

            payload = json.loads(payload_str)

            # Apply settings to known node IDs
            if "92:3" in payload:
                payload["92:3"]["inputs"]["text"] = input_prompt.strip() or payload["92:3"]["inputs"].get("text", "")

            if "92:1" in payload:
                payload["92:1"]["inputs"]["ckpt_name"] = checkpoint_name
                debug_lines.append(f"Checkpoint set: {checkpoint_name} (92:1)")

            # Also set related loaders for safety/consistency
            for nid in ["92:48", "92:60"]:
                if nid in payload and "ckpt_name" in payload[nid]["inputs"]:
                    payload[nid]["inputs"]["ckpt_name"] = checkpoint_name

            if "92:62" in payload:
                payload["92:62"]["inputs"]["value"] = video_length
                debug_lines.append(f"Length set: {video_length} (92:62)")

            for nid in ["92:22", "92:51", "92:97"]:
                if nid in payload:
                    key = "frame_rate" if nid in ["92:22", "92:51"] else "fps"
                    if key in payload[nid]["inputs"]:
                        payload[nid]["inputs"][key] = fps
                        debug_lines.append(f"FPS/frame_rate set: {fps} ({nid})")

            # Resolution: force the resize node + longer_edge fallback
            if "102" in payload:
                payload["102"]["inputs"]["resize_type.width"] = width
                payload["102"]["inputs"]["resize_type.height"] = height
                debug_lines.append(f"Input resize forced: {width}x{height} (102)")

            if "92:106" in payload:
                longer = max(width, height, 1536)
                payload["92:106"]["inputs"]["longer_edge"] = longer
                debug_lines.append(f"Longer edge set to {longer} (92:106)")

            base_payload = {"prompt": payload}

            queued_ids = []

            if all([project, sequence, shot, name]):
                input_dir = os.path.join(LOADIMAGE_DIR, project, sequence, shot)
                debug_lines.append(f"Input dir: {input_dir}")

                if not os.path.exists(input_dir):
                    debug_lines.append("Input dir missing → queuing fallback job")
                else:
                    image_extensions = ('.png', '.jpg', '.jpeg')
                    all_images = [
                        f for f in os.listdir(input_dir)
                        if f.lower().endswith(image_extensions) and f.startswith(name + "__")
                    ]

                    to_process = []
                    for img in all_images:
                        match = re.match(rf'^{re.escape(name)}__(\d+)_?\.', img, re.IGNORECASE)
                        if not match:
                            continue
                        frame_num = match.group(1)
                        vid_pattern = os.path.join(input_dir, f"{name}__{frame_num}__*.mp4")

                        existing_videos = glob.glob(vid_pattern)
                        if existing_videos and not regenerate:
                            debug_lines.append(f"Skipping {img} — video already exists ({os.path.basename(existing_videos[0])})")
                            continue

                        if existing_videos and regenerate:
                            debug_lines.append(f"Regenerate ON → will overwrite existing video for {img}")
                        
                        to_process.append(img)

                    if not to_process:
                        debug_lines.append("No images to process (all skipped or already done)")
                        # Optional: still queue one job if user wants to force something
                        # but for now we skip queuing if nothing to do
                    else:
                        debug_lines.append(f"Processing {len(to_process)} image(s)")
                        for image_file in to_process:
                            job_payload = json.loads(json.dumps(base_payload))
                            job_prompt = job_payload["prompt"]

                            full_img_path = os.path.join(input_dir, image_file)
                            if "98" in job_prompt:
                                job_prompt["98"]["inputs"]["image"] = full_img_path
                                debug_lines.append(f"Image set: {image_file} (98)")

                            basename = os.path.splitext(image_file)[0]
                            prefix = f"{project}/{sequence}/{shot}/{basename}"
                            if "75" in job_prompt:
                                job_prompt["75"]["inputs"]["filename_prefix"] = prefix
                                debug_lines.append(f"Output prefix: {prefix} (75)")

                            job_payload["client_id"] = str(uuid.uuid4())
                            if requests:
                                r = requests.post(f"http://{host}/prompt", json=job_payload)
                                if r.ok:
                                    queued_ids.append(r.json().get("prompt_id"))
                                else:
                                    debug_lines.append(f"Queue failed for {image_file}: {r.status_code} {r.text}")

            else:
                debug_lines.append("No project/seq/shot/name → queuing single job")
                job_payload = json.loads(json.dumps(base_payload))
                job_payload["client_id"] = str(uuid.uuid4())
                if requests:
                    r = requests.post(f"http://{host}/prompt", json=job_payload)
                    if r.ok:
                        queued_ids.append(r.json().get("prompt_id"))
                    else:
                        debug_lines.append(f"Single queue failed: {r.status_code} {r.text}")

            returned_json = json.dumps({'queued_ids': queued_ids})
            debug_lines.append(f"Queued {len(queued_ids)} job(s)")

            debug_lines.append("=== DEBUG END ===")
            return ("\n".join(debug_lines), returned_json, 1 if queued_ids else 0)

        except Exception as e:
            import traceback
            debug_lines.append(f"Error: {str(e)}")
            debug_lines.append(traceback.format_exc())
            return ("\n".join(debug_lines), None, 0)


NODE_CLASS_MAPPINGS = {"CT_LTX2_i2v_trigger": CT_LTX2_i2v_trigger}
NODE_DISPLAY_NAME_MAPPINGS = {"CT_LTX2_i2v_trigger": "ct_ltx2_i2v"}