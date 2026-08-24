---
frameworks:
- Pytorch
license: Apache License 2.0
tags:
  - Qwen3.5
  - qwen3_5
base_model_relation: quantized
tasks:
  - image-text-to-text

base_model:
  - Qwen/Qwen3.5-2B
---
### Quantization
#### This model is created by quantizing Qwen/Qwen3.5-2B to Q4_K_M using convert_hf_to_gguf.py and llama-quantize from llama.cpp.

### Target Users
#### This model supports CPU and heterogeneous (CPU+GPU) inference deployment, making it suitable for users without a GPU.

### Usage Steps
#### 1. Download
SDK Download
```bash
# Install ModelScope
pip install modelscope
```
```python
# Download the model with SDK
from modelscope import snapshot_download
model_dir = snapshot_download('diodel/Qwen3.5-2B-Q4_K_M-GGUF')
```
Git Download
```bash
# Download the model with Git
git clone https://www.modelscope.cn/diodel/Qwen3.5-2B-Q4_K_M-GGUF.git
```
For more download methods, please refer to the official documentation: https://modelscope.cn/docs/models/download
#### 2. Prepare llama.cpp dependencies

#### 3. Build and Start the Service
```
# Build and start the service
./llama.cpp/build/bin/llama-server \
    --model ./Qwen3.5-2B-Q4_K_M.gguf \
    --ctx-size 2048 \
    --host 0.0.0.0 \
    --port 8000
```