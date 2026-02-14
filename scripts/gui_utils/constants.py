# gui_utils/constants.py

JOBTYPE_HOST_MAPPING = {
    'ct_flux_t2i':           'FLUX_HOST',
    'ct_wan2_5s':            'WAN_HOST',
    'ct_qwen_i2i':           'QWEN_HOST',
    'ct_qwen_cameratransform': 'QWEN_HOST',
    'ct_ltx2_i2v':           'LTX_HOST',
}

JOBTYPE_LIST = [
    "Select Jobtype",
    "ct_flux_t2i",
    "ct_wan2_5s",
    "ct_qwen_i2i",
    "ct_qwen_cameratransform",
    "ct_ltx2_i2v",
]

DEFAULT_JOBTYPE = "ct_flux_t2i"