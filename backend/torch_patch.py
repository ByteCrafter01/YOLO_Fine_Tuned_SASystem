import torch

_original_torch_load = torch.load

def patched_torch_load(f, map_location=None, pickle_module=None, **kwargs):
    kwargs['weights_only'] = False
    return _original_torch_load(f, map_location=map_location, pickle_module=pickle_module, **kwargs)

torch.load = patched_torch_load

print("PyTorch loading patched for YOLO compatibility (weights_only=False)")