#!/usr/bin/env python3
# Internal Queuer - Runs inside container. Receives JSON via stdin, handles FS/API/runners.
import json
import os
import sys
import importlib.util
import shutil
import glob
from io import StringIO

# Relative paths (from scripts/ -> root)
ROOT_DIR = os.path.dirname(os.path.dirname(__file__))
NODES_DIR = os.path.join(ROOT_DIR, 'nodes')
WORKFLOWS_DIR = os.path.join(ROOT_DIR, 'workflows')
ASSETS_DIR = os.path.join(ROOT_DIR, 'assets')
DUMMY_IMAGE_PATH = os.path.join(ASSETS_DIR, 'dummy_image.png')

# Globals (container-fixed)
HOST_OUTPUT_DIR = os.getenv('COMFYUI_OUTPUT', '/ComfyUI/output')
jobtype_to_json = {
    'ct_flux_t2i': os.path.join(WORKFLOWS_DIR, 'ct_flux_t2i_base.json'),
    'ct_wan2_5s': os.path.join(WORKFLOWS_DIR, 'ct_wan2_5s_base.json'),
    'ct_qwen_i2i': os.path.join(WORKFLOWS_DIR, 'ct_qwen_i2i_base.json'),
}
jobtype_to_py = {
    'ct_flux_t2i': 'ct_flux_t2i.py',
    'ct_wan2_5s': 'ct_wan2_5s.py',
    'ct_qwen_i2i': 'ct_qwen_i2i_base.py',
}
class_name_mapping = {
    'ct_flux_t2i': 'WorkflowTrigger',
    'ct_wan2_5s': 'CT_WAN_TRIGGER',
    'ct_qwen_i2i': 'WorkflowTrigger',
}

def load_runner_for_jobtype(jobtype: str):
    py_filename = jobtype_to_py.get(jobtype, f"{jobtype}.py")
    py_path = os.path.join(NODES_DIR, py_filename)
    if not os.path.exists(py_path):
        raise FileNotFoundError(f"❌ .py file not found: {py_path} for JOBTYPE '{jobtype}'")
    spec = importlib.util.spec_from_file_location(jobtype, py_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[jobtype] = module
    spec.loader.exec_module(module)
    expected_class_name = class_name_mapping.get(jobtype, 'WorkflowTrigger')
    if not hasattr(module, expected_class_name):
        raise AttributeError(f"❌ '{expected_class_name}' class not found in {py_filename}")
    if not hasattr(module, 'extract_prompt_from_workflow'):
        raise AttributeError(f"❌ 'extract_prompt_from_workflow' function not found in {py_filename}")
    globals()['extract_prompt_from_workflow'] = module.extract_prompt_from_workflow
    return getattr(module, expected_class_name)()

def create_shot_dirs(project, sequences_to_run):
    """Create dirs inside container output."""
    for seq in sequences_to_run:
        dir_path = os.path.join(HOST_OUTPUT_DIR, project, seq)
        os.makedirs(dir_path, exist_ok=True)
        print(f"📁 Created dir: {dir_path}")

def copy_dummies_to_shot(project, seq, shot_id, name, flux_iterations):
    """Copy dummies, return paths for cleanup."""
    shot_dir = os.path.join(HOST_OUTPUT_DIR, project, seq, shot_id)
    existing_images = glob.glob(os.path.join(shot_dir, f"{name}__?????.png"))
    max_num = 0
    for img in existing_images:
        try:
            num_str = os.path.basename(img).split('__')[1].split('_')[0]
            num = int(num_str)
            max_num = max(max_num, num)
        except (IndexError, ValueError):
            continue
    start_num = max_num + 1
    copied = []
    if not os.path.exists(DUMMY_IMAGE_PATH):
        print(f"❌ Dummy image not found at {DUMMY_IMAGE_PATH}")
        return copied
    for i in range(flux_iterations):
        num = start_num + i
        target = os.path.join(shot_dir, f"{name}__{num:05d}_.png")
        shutil.copy2(DUMMY_IMAGE_PATH, target)
        copied.append(target)
        print(f"📄 Copied dummy to {target}")
    return copied

def delete_dummies_from_shot(project, seq, shot_id, name, copied_dummies):
    shot_dir = os.path.join(HOST_OUTPUT_DIR, project, seq, shot_id)
    for dummy in copied_dummies:
        if os.path.exists(dummy):
            os.remove(dummy)
            print(f"🗑️ Deleted dummy {dummy}")

def queue_jobs_internal(data):
    """Process job list from JSON."""
    jobs = data['jobs']
    host = data['host']
    results = []
    sequences_to_run = list(set(j['sequence'] for j in jobs))
    create_shot_dirs(data['jobs'][0]['project'], sequences_to_run)  # Once
    for job in jobs:
        jt = job['jt']
        project, seq, shot_id, subshot_id = job['project'], job['sequence'], job['shot_id'], job['subshot_id']
        shot_data, num_jobs = job['shot_data'], job['num_jobs']
        workflow_json, width, height, name = job['workflow_json'], job['width'], job['height'], job['name']
        print(f"\n🔄 Queueing {jt}: {project}/{seq}/{shot_id}/{subshot_id} ({num_jobs} jobs)")
        json_file = jobtype_to_json[jt]
        runner = load_runner_for_jobtype(jt)
        copied_dummies = None
        if 'wan' in jt.lower():
            flux_iterations = int(shot_data.get('FLUX_ITERATIONS', job['globals'].get('FLUX_ITERATIONS', 1)))
            copied_dummies = copy_dummies_to_shot(project, seq, shot_id, name, flux_iterations)
        try:
            debug_lines, returned_json, success = runner.execute(
                workflow_json=workflow_json, host=host, width=width, height=height, json_file=json_file,
                num_jobs=num_jobs, project=project, sequence=seq, shot=shot_id, name=name
            )
            print(f" {jt.capitalize()}: Success={success} | Jobs queued: {num_jobs}")
            print(f" Debug: {debug_lines[:200]}...")
            results.append({'debug_lines': debug_lines, 'returned_json': returned_json, 'success': success, 'queued_ids': json.loads(returned_json)['queued_ids'] if returned_json else []})
        except Exception as e:
            print(f"❌ Error queuing {jt}: {e}")
            results.append({'success': 0, 'error': str(e)})
        if copied_dummies:
            delete_dummies_from_shot(project, seq, shot_id, name, copied_dummies)
    print(f"✅ Internal: Processed {len(results)} jobs")
    return results

if __name__ == "__main__":
    input_json = sys.stdin.read().strip()
    if not input_json:
        print(json.dumps([]))
        sys.exit(1)
    data = json.loads(input_json)
    results = queue_jobs_internal(data)
    print(json.dumps(results))