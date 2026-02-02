# ct_storytools/__init__.py - Root-level node registration (modular, no subdir)
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

# Flux node
try:
    from .ct_flux_t2i import WorkflowTrigger
    NODE_CLASS_MAPPINGS["WorkflowTrigger"] = WorkflowTrigger
    NODE_DISPLAY_NAME_MAPPINGS["WorkflowTrigger"] = "ct_flux_t2i"
    print("Registered: WorkflowTrigger (flux)")
except ImportError as e:
    print(f"Flux registration failed: {e}")

# Wan node
try:
    from .ct_wan2_5s import CT_WAN_TRIGGER
    NODE_CLASS_MAPPINGS["CT_WAN_TRIGGER"] = CT_WAN_TRIGGER
    NODE_DISPLAY_NAME_MAPPINGS["CT_WAN_TRIGGER"] = "ct_wan2_5s"
    print("Registered: CT_WAN_TRIGGER (wan)")
except ImportError as e:
    print(f"Wan registration failed: {e}")

# FS node
try:
    from .fs_utils import FSUtilsNode
    NODE_CLASS_MAPPINGS["FSUtilsNode"] = FSUtilsNode
    NODE_DISPLAY_NAME_MAPPINGS["FSUtilsNode"] = "CT FS Utils"
    print("Registered: FSUtilsNode (FS)")
except ImportError as e:
    print(f"FS registration failed: {e}")

# serverside execution node
try:
    from .ct_serverside_execution import CTServersideExecution
    NODE_CLASS_MAPPINGS["CTServersideExecution"] = CTServersideExecution
    NODE_DISPLAY_NAME_MAPPINGS["CTServersideExecution"] = "CT Serverside Execution"
    print("Registered: CTServersideExecution Node")
except ImportError as e:
    print(f"Serverside execution registration failed: {e}")

# Qwen camera transform node
try:
    from .ct_qwen_cameratransform import QwenCameraTrigger
    NODE_CLASS_MAPPINGS["QwenCameraTrigger"] = QwenCameraTrigger
    NODE_DISPLAY_NAME_MAPPINGS["QwenCameraTrigger"] = "ct_qwen_cameratransform"
    print("Registered: QwenCameraTrigger (qwen camera)")
except ImportError as e:
    print(f"Qwen camera transform registration failed: {e}")

# Final debug
total = len(NODE_CLASS_MAPPINGS)
print(f"ct_storytools: Registered {total} nodes: {list(NODE_CLASS_MAPPINGS.keys())}")
print("DEBUG: reached end of ct_storytools __init__.py")

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]