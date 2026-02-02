import json
import os
import uuid
import time
import random
import glob
try:
    import requests
except ImportError:
    requests = None


class QwenCameraTrigger:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["TT", "5angles", "10angles", "20angles", "CharacterSheet"], {
                    "default": "TT"
                }),
                "host": ("STRING", {"default": "127.0.0.1:8188"}),
                "input_dir": ("STRING", {"default": "input", "multiline": False}),
                "project": ("STRING", {"default": "project"}),
                "sequence": ("STRING", {"default": "seq"}),
                "shot": ("STRING", {"default": "shot"}),
                "name": ("STRING", {"default": "char"}),
            },
            "optional": {
                "json_file": ("STRING", {"default": "", "multiline": False}),
                "seed_base": ("INT", {"default": 123456789, "min": 0, "max": 2**31-1}),
            }
        }

    RETURN_TYPES = ("STRING", "STRING", "INT")
    RETURN_NAMES = ("debug_output", "status", "jobs_queued")
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = True

    def execute(self, mode, host, input_dir, project, sequence, shot, name,
                json_file="", seed_base=123456789):

        print("[QwenCam] === execute() STARTED ===")
        print(f"[QwenCam] mode={mode}  host={host}  json_file='{json_file}'")

        debug = []
        debug.append("=== ct_qwen_cameratransform ===")
        debug.append(f"Mode : {mode}")
        debug.append(f"Host : {host}")
        debug.append(f"Pattern : {project}/{sequence}/{shot}/{name}*.png")

        jobs_queued = 0
        errors = []

        try:
            print("[QwenCam] Step 1: Locating base workflow")
            if not json_file:
                json_file = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'ct_storytools', 'workflows', 'ct_qwen_cameratransform_base.json'
                )
            print(f"[QwenCam] Using workflow path: {json_file}")

            if not os.path.exists(json_file):
                raise FileNotFoundError(f"Base workflow not found: {json_file}")

            print("[QwenCam] Step 2: Loading JSON")
            with open(json_file, 'r', encoding='utf-8') as f:
                base_workflow = json.load(f)
            print("[QwenCam] JSON loaded successfully")

            debug.append(f"Loaded base workflow: {json_file}")

            print("[QwenCam] Step 3: Finding input images")
            search_pattern = os.path.join(input_dir, project, sequence, shot, f"{name}*.png")
            image_paths = sorted(glob.glob(search_pattern))
            print(f"[QwenCam] Found {len(image_paths)} images matching: {search_pattern}")

            if not image_paths:
                debug.append(f"No images found for pattern: {search_pattern}")
                print("[QwenCam] No images → early return")
                return ("\n".join(debug), "No matching images", 0)

            debug.append(f"Found {len(image_paths)} input image(s)")

            print("[QwenCam] Step 4: Preparing camera combinations")
            combinations = []
            # ... (your existing combinations logic remains unchanged)
            # TT / random / preset_views code here ...
            debug.append(f"→ Generating {len(combinations)} camera setups per input image")
            print(f"[QwenCam] Generated {len(combinations)} camera angles")

            queued_ids = []

            for img_idx, full_img_path in enumerate(image_paths, 1):
                filename = os.path.basename(full_img_path)
                print(f"[QwenCam] Processing image {img_idx}/{len(image_paths)} : {filename}")

                for cam_idx, (h_angle, v_angle, zoom) in enumerate(combinations, 1):
                    print(f"[QwenCam]   → Cam {cam_idx}/{len(combinations)}  h={h_angle:.1f} v={v_angle:.1f} z={zoom:.1f}")

                    # Deep copy
                    print("[QwenCam]     Deep copying workflow...")
                    workflow = json.loads(json.dumps(base_workflow))

                    # Replace image
                    if "8" in workflow and workflow["8"].get("class_type") == "LoadImage":
                        print("[QwenCam]     Setting LoadImage filename")
                        workflow["8"]["inputs"]["image"] = filename

                    # Set camera
                    if "4" in workflow and workflow["4"].get("class_type") == "QwenMultiangleCameraNode":
                        print("[QwenCam]     Setting camera parameters")
                        workflow["4"]["inputs"]["horizontal_angle"] = round(float(h_angle), 2)
                        workflow["4"]["inputs"]["vertical_angle"]   = round(float(v_angle), 2)
                        workflow["4"]["inputs"]["zoom"]             = round(float(zoom), 2)
                        workflow["4"]["inputs"]["default_prompts"]  = False

                    # Seed
                    seed = seed_base + (img_idx * 100000) + (cam_idx * 1000)
                    if "2:105" in workflow and workflow["2:105"].get("class_type") == "KSampler":
                        print(f"[QwenCam]     Setting seed = {seed}")
                        workflow["2:105"]["inputs"]["seed"] = seed

                    # Prefix
                    prefix = f"{project}/{sequence}/{shot}/{name}_{mode}_i{img_idx:02d}_c{cam_idx:03d}_h{int(h_angle):03d}_v{int(v_angle):+03d}_z{zoom:.1f}_"
                    print(f"[QwenCam]     Setting SaveImage prefix: {prefix}")
                    for node_id, node in workflow.items():
                        if node.get("class_type") == "SaveImage":
                            node["inputs"]["filename_prefix"] = prefix

                    # Queue
                    print("[QwenCam]     Preparing payload and sending to ComfyUI...")
                    payload = {"prompt": workflow}
                    payload["client_id"] = str(uuid.uuid4())

                    if not requests:
                        print("[QwenCam]     requests library missing!")
                        errors.append("requests library missing")
                        continue

                    try:
                        resp = requests.post(f"http://{host}/prompt", json=payload, timeout=12)
                        print(f"[QwenCam]     Response status: {resp.status_code}")
                        if resp.ok:
                            prompt_id = resp.json().get("prompt_id")
                            queued_ids.append(prompt_id)
                            jobs_queued += 1
                            debug.append(f" Queued → {prompt_id[:8]} h={h_angle:3.0f}° v={v_angle:3.0f}° z={zoom:4.1f}")
                            print(f"[QwenCam]     Success - queued prompt_id: {prompt_id}")
                        else:
                            print(f"[QwenCam]     Queue failed: {resp.status_code} {resp.text[:120]}")
                            errors.append(f"Queue failed cam {cam_idx}: {resp.status_code} {resp.text[:80]}")
                    except Exception as req_e:
                        print(f"[QwenCam]     Request exception: {type(req_e).__name__} - {str(req_e)}")
                        errors.append(f"Request exception cam {cam_idx}: {str(req_e)}")

            print(f"[QwenCam] All jobs processed - queued {jobs_queued}")
            status_msg = f"Queued {jobs_queued} jobs | {len(errors)} errors"
            debug.append(f"Finished → {status_msg}")

            print("[QwenCam] === execute() FINISHED normally ===")
            return ("\n".join(debug), status_msg, jobs_queued)

        except Exception as e:
            print(f"[QwenCam] !!! EXCEPTION in execute(): {type(e).__name__} - {str(e)}")
            import traceback
            tb = traceback.format_exc()
            print("[QwenCam] Full traceback:")
            print(tb)
            debug.append("Exception occurred:")
            debug.append(tb.strip())
            print("[QwenCam] === execute() FINISHED with exception ===")
            return ("\n".join(debug), "Execution failed", jobs_queued)


# Registration (used when the file is imported directly)
NODE_CLASS_MAPPINGS = {"QwenCameraTrigger": QwenCameraTrigger}
NODE_DISPLAY_NAME_MAPPINGS = {"ct_qwen_cameratransform": "ct_qwen_cameratransform"}