#!/bin/bash

# Updated Script to install ComfyUI custom nodes: Crystools, Radiance, VideoHelperSuite, essentials, RES4LYF, controlnet_aux, rgthree-comfy, Easy-Use, KJNodes, a-person-mask-generator, CaptionThis, AdvancedLivePortrait, SeedVR2_VideoUpscaler, facerestore_cf, ComfyUI-GGUF, ComfyUI Queue Manager, and sync ct_storytools folder
# Handles numpy pinning to avoid conflicts with ComfyUI dependencies (e.g., numba, gpytoolbox)
# Place this script in /ComfyUI/input/install
# Run it from within the container (e.g., from ComfyUI root or anywhere, as it uses absolute paths)
# Assumes git, pip, and apt are available in the container

set -e  # Exit on any error

echo "Starting custom nodes installation..."

# Install rsync if not available (assuming apt-based container like Ubuntu/Debian)
if ! command -v rsync &> /dev/null; then
    echo "rsync not found, installing via apt..."
    apt-get update -qq && apt-get install -y rsync
else
    echo "rsync is already available."
fi

# Define paths
COMFYUI_ROOT="/ComfyUI"
CUSTOM_NODES_DIR="${COMFYUI_ROOT}/custom_nodes"
INSTALL_DIR="${COMFYUI_ROOT}/input/install"
STORYTOOLS_SOURCE="${INSTALL_DIR}/ct_storytools"
STORYTOOLS_DEST="${CUSTOM_NODES_DIR}/ct_storytools"

# Create global constraints file to pin numpy for all installs
cd "${CUSTOM_NODES_DIR}"
echo "numpy==1.26.4" > constraints.txt

# Function to install a node
install_node() {
    local repo_url="$1"
    local dir_name="$2"
    local display_name="$3"
    
    local node_dir="${CUSTOM_NODES_DIR}/${dir_name}"
    if [ ! -d "${node_dir}" ]; then
        echo "Cloning ${display_name}..."
        git clone "${repo_url}" "${dir_name}"
    else
        echo "${display_name} already exists, skipping clone."
    fi
    
    cd "${node_dir}"
    if [ -f "requirements.txt" ]; then
        echo "Installing requirements for ${display_name} with numpy pinned..."
        pip install -r requirements.txt -c ../constraints.txt
    else
        echo "No requirements.txt found for ${display_name}, skipping pip install."
    fi
    cd "${CUSTOM_NODES_DIR}"
}

# Install ComfyUI-Crystools
install_node "https://github.com/crystian/ComfyUI-Crystools.git" "ComfyUI-Crystools" "ComfyUI-Crystools"

# Install Radiance
install_node "https://github.com/fxtdstudios/radiance.git" "radiance" "Radiance"

# Install additional nodes
install_node "https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git" "ComfyUI-VideoHelperSuite" "ComfyUI-VideoHelperSuite"
install_node "https://github.com/cubiq/ComfyUI_essentials.git" "ComfyUI_essentials" "ComfyUI_essentials"
install_node "https://github.com/ClownsharkBatwing/RES4LYF.git" "RES4LYF" "RES4LYF"
install_node "https://github.com/Fannovel16/comfyui_controlnet_aux.git" "comfyui_controlnet_aux" "comfyui_controlnet_aux"
install_node "https://github.com/rgthree/rgthree-comfy.git" "rgthree-comfy" "rgthree-comfy"
install_node "https://github.com/yolain/ComfyUI-Easy-Use.git" "ComfyUI-Easy-Use" "ComfyUI-Easy-Use"
install_node "https://github.com/kijai/ComfyUI-KJNodes.git" "ComfyUI-KJNodes" "ComfyUI-KJNodes"
install_node "https://github.com/djbielejeski/a-person-mask-generator.git" "a-person-mask-generator" "a-person-mask-generator"
install_node "https://github.com/MieMieeeee/ComfyUI-CaptionThis.git" "ComfyUI-CaptionThis" "ComfyUI-CaptionThis"
install_node "https://github.com/PowerHouseMan/ComfyUI-AdvancedLivePortrait.git" "ComfyUI-AdvancedLivePortrait" "ComfyUI-AdvancedLivePortrait"
install_node "https://github.com/numz/ComfyUI-SeedVR2_VideoUpscaler.git" "ComfyUI-SeedVR2_VideoUpscaler" "ComfyUI-SeedVR2_VideoUpscaler"
install_node "https://github.com/mav-rik/facerestore_cf.git" "facerestore_cf" "Facerestore CF (Code Former)"
install_node "https://github.com/city96/ComfyUI-GGUF.git" "ComfyUI-GGUF" "ComfyUI-GGUF (gguf)"
install_node "https://github.com/QuietNoise/comfyui_queue_manager.git" "comfyui_queue_manager" "ComfyUI Queue Manager"
install_node "https://github.com/jtydhr88/ComfyUI-qwenmultiangle" "comfyui-qwenmultiangle" "comfyui-qwenmultiangle"
install_node "https://github.com/christiansjostedt/ct_storytools.git" "ct_storytools" "ct_storytools"

# Sync ct_storytools folder (always sync if source exists, to update changes or create if missing)
#if [ -d "${STORYTOOLS_SOURCE}" ]; then
#    echo "Syncing ct_storytools folder to custom_nodes..."
#    rsync -av "${STORYTOOLS_SOURCE}/" "${STORYTOOLS_DEST}/"
#else
#    echo "Source ct_storytools folder not found, skipping sync."
#fi

# Clean up constraints file
rm constraints.txt

echo "Installation complete! Restart ComfyUI to load the new nodes."
echo "Note: If you encounter numpy-related errors post-install, run 'pip install numpy==1.26.4 --force-reinstall' to ensure compatibility."