# fs_utils.py - Portable FS Utils Node for Dir Creation & Dummy Copy/Delete
import os
import shutil
import glob
import json

class FSUtilsNode:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "mode": (["create_dir", "copy_dummies", "delete_dummies"], {"default": "create_dir"}),
                "project": ("STRING", {"default": "project", "multiline": False}),
                "sequence": ("STRING", {"default": "seq", "multiline": False}),
                "shot": ("STRING", {"default": "shot", "multiline": False}),
                "name": ("STRING", {"default": "name", "multiline": False}),
                "flux_iterations": ("INT", {"default": 1, "min": 1, "max": 100}),
                "dummy_path": ("STRING", {"default": "/ComfyUI/custom_nodes/ct_storytools/assets/dummy_image.png", "multiline": False}),
                "output_base": ("STRING", {"default": "/ComfyUI/output", "multiline": False}),
            },
            "optional": {
                "copied_dummies": ("STRING", {"default": "", "multiline": False}),
                "timestamp": ("INT", {"default": 0, "min": 0, "max": 9999999999}),  # Cache-buster: unique per run
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("debug_output",)
    FUNCTION = "execute"
    CATEGORY = "ct_tools"
    OUTPUT_NODE = False

    def execute(
        self, mode, project, sequence, shot, name, flux_iterations=1,
        dummy_path="", output_base="/ComfyUI/output", copied_dummies="", timestamp=0
    ):
        debug_lines = [f"FS Timestamp: {timestamp}"]  # Log to confirm uniqueness
        try:
            if mode == "create_dir":
                dir_path = os.path.join(output_base, project, sequence, shot)
                # Optional: Append timestamp to path for uniqueness (e.g., /output/project/seq/shot_t12345)
                # dir_path += f"_t{timestamp}"  # Uncomment if needed for multi-run dirs
                os.makedirs(dir_path, exist_ok=True)
                debug_lines.append(f"📁 Created dir: {dir_path}")
            elif mode == "copy_dummies":
                if not os.path.exists(dummy_path):
                    raise FileNotFoundError(f"Dummy missing: {dummy_path}")
                shot_dir = os.path.join(output_base, project, sequence, shot)
                existing = glob.glob(os.path.join(shot_dir, f"{name}__?????.png"))
                max_num = 0
                for img in existing:
                    try:
                        num_str = os.path.basename(img).split('__')[1].split('_')[0]
                        max_num = max(max_num, int(num_str))
                    except (IndexError, ValueError):
                        continue
                start_num = max_num + 1
                copied = []
                for i in range(flux_iterations):
                    num = start_num + i
                    target = os.path.join(shot_dir, f"{name}__{num:05d}_.png")
                    shutil.copy2(dummy_path, target)
                    copied.append(target)
                    debug_lines.append(f"📄 Copied dummy: {target}")
                copied_json = json.dumps({"copied_dummies": copied})
                debug_lines.append(f"✅ Copied {len(copied)} dummies")
                return (copied_json,)
            elif mode == "delete_dummies":
                if copied_dummies:
                    copied_list = json.loads(copied_dummies)
                    for dummy in copied_list:
                        if os.path.exists(dummy):
                            os.remove(dummy)
                            debug_lines.append(f"🗑️ Deleted: {dummy}")
                else:
                    debug_lines.append("⚠️ No dummies to delete")
            return ("\n".join(debug_lines),)
        except Exception as e:
            import traceback
            debug_lines.append(f"❌ FS Error: {str(e)}")
            debug_lines.append(traceback.format_exc())
            return ("\n".join(debug_lines),)

# LOCAL MAPPINGS ONLY - No built-ins!
NODE_CLASS_MAPPINGS = {"FSUtilsNode": FSUtilsNode}
NODE_DISPLAY_NAME_MAPPINGS = {"FSUtilsNode": "CT FS Utils"}
