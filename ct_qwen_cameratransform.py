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

        debug = []
        debug.append("=== ct_qwen_cameratransform ===")
        debug.append(f"Mode          : {mode}")
        debug.append(f"Host          : {host}")
        debug.append(f"Pattern       : {project}/{sequence}/{shot}/{name}*.png")

        jobs_queued = 0
        errors = []

        try:
            # ─── Locate base workflow ───────────────────────────────────────
            if not json_file:
                json_file = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    'ct_storytools', 'workflows', 'ct_qwen_cameratransform_base.json'
                )

            if not os.path.exists(json_file):
                raise FileNotFoundError(f"Base workflow not found: {json_file}")

            with open(json_file, 'r', encoding='utf-8') as f:
                base_workflow = json.load(f)

            debug.append(f"Loaded base workflow: {json_file}")

            # ─── Find input images ──────────────────────────────────────────
            search_pattern = os.path.join(input_dir, project, sequence, shot, f"{name}*.png")
            image_paths = sorted(glob.glob(search_pattern))

            if not image_paths:
                debug.append(f"No images found for pattern: {search_pattern}")
                return ("\n".join(debug), "No matching images", 0)

            debug.append(f"Found {len(image_paths)} input image(s)")

            # ─── Prepare angle/zoom combinations per mode ───────────────────
            combinations = []

            if mode == "TT":
                # 36 frames → 10° steps (classic turntable)
                for i in range(36):
                    h_angle = i * 10
                    combinations.append((h_angle, 0, 5.0))   # fixed vertical & zoom

            elif mode in ("5angles", "10angles", "20angles"):
                count = {"5angles": 5, "10angles": 10, "20angles": 20}[mode]
                for _ in range(count):
                    h = random.uniform(0, 360)
                    v = random.uniform(-30, 60)
                    z = random.uniform(2.5, 7.5)
                    combinations.append((h, v, z))

            elif mode == "CharacterSheet":
                # 20 preset views – feel free to tune these angles
                preset_views = [
                    (0,    0,   5.0),    # front
                    (45,   0,   5.0),    # 3/4 right
                    (90,   0,   5.0),    # right profile
                    (135,  0,   5.0),
                    (180,  0,   5.0),    # back
                    (225,  0,   5.0),
                    (270,  0,   5.0),    # left profile
                    (315,  0,   5.0),
                    (0,   35,   4.2),    # front looking up
                    (0,  -25,   5.8),    # front looking down
                    (90,  20,   4.8),
                    (270, 20,   4.8),
                    (45,  25,   4.0),
                    (135, 25,   4.0),
                    (0,    0,   3.2),    # closer front
                    (0,    0,   7.0),    # farther front
                    (180, 15,   5.0),
                    (90, -20,   5.2),
                    (270,-20,   5.2),
                    (0,   50,   3.5),    # strong up angle
                ]
                combinations = preset_views  # exactly 20

            debug.append(f"→ Generating {len(combinations)} camera setups per input image")

            queued_ids = []

            for img_idx, full_img_path in enumerate(image_paths, 1):
                rel_path = os.path.relpath(full_img_path, input_dir).replace("\\", "/")
                filename = os.path.basename(full_img_path)

                debug.append(f"  Processing image {img_idx}/{len(image_paths)} : {rel_path}")

                for cam_idx, (h_angle, v_angle, zoom) in enumerate(combinations, 1):
                    # Deep copy workflow
                    workflow = json.loads(json.dumps(base_workflow))

                    # 1. Replace input image filename (node "8")
                    if "8" in workflow and workflow["8"].get("class_type") == "LoadImage":
                        workflow["8"]["inputs"]["image"] = filename

                    # 2. Set camera parameters (node "4" = QwenMultiangleCameraNode)
                    if "4" in workflow and workflow["4"].get("class_type") == "QwenMultiangleCameraNode":
                        workflow["4"]["inputs"]["horizontal_angle"] = round(float(h_angle), 2)
                        workflow["4"]["inputs"]["vertical_angle"]   = round(float(v_angle), 2)
                        workflow["4"]["inputs"]["zoom"]             = round(float(zoom), 2)
                        workflow["4"]["inputs"]["default_prompts"]  = False

                    # 3. Optional: slight seed variation per job
                    seed = seed_base + (img_idx * 100000) + (cam_idx * 1000)

                    if "2:105" in workflow and workflow["2:105"].get("class_type") == "KSampler":
                        workflow["2:105"]["inputs"]["seed"] = seed

                    # 4. Structured filename prefix → creates folders project/seq/shot/...
                    prefix = f"{project}/{sequence}/{shot}/{name}_{mode}_i{img_idx:02d}_c{cam_idx:03d}_h{int(h_angle):03d}_v{int(v_angle):+03d}_z{zoom:.1f}_"

                    for node_id, node in workflow.items():
                        if node.get("class_type") == "SaveImage":
                            node["inputs"]["filename_prefix"] = prefix

                    # 5. Queue the job
                    payload = {"prompt": workflow}
                    payload["client_id"] = str(uuid.uuid4())

                    if not requests:
                        errors.append("requests library missing")
                        continue

                    try:
                        resp = requests.post(f"http://{host}/prompt", json=payload, timeout=12)
                        if resp.ok:
                            prompt_id = resp.json().get("prompt_id")
                            queued_ids.append(prompt_id)
                            jobs_queued += 1
                            debug.append(f"    Queued → {prompt_id[:8]}  h={h_angle:3.0f}° v={v_angle:3.0f}° z={zoom:4.1f}")
                        else:
                            errors.append(f"Queue failed cam {cam_idx}: {resp.status_code} {resp.text[:80]}")
                    except Exception as e:
                        errors.append(f"Request exception cam {cam_idx}: {str(e)}")

            status_msg = f"Queued {jobs_queued} jobs | {len(errors)} errors"
            debug.append(f"Finished → {status_msg}")

            return ("\n".join(debug), status_msg, jobs_queued)

        except Exception as e:
            import traceback
            debug.append("Exception occurred:")
            debug.append(traceback.format_exc().strip())
            return ("\n".join(debug), "Execution failed", jobs_queued)


# Registration (used when the file is imported directly)
NODE_CLASS_MAPPINGS = {"QwenCameraTrigger": QwenCameraTrigger}
NODE_DISPLAY_NAME_MAPPINGS = {"ct_qwen_cameratransform": "ct_qwen_cameratransform"}