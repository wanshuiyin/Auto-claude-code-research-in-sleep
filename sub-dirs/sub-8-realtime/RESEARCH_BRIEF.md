# Research Brief: Fast and Lightweight MRI Motion Correction

## Problem Statement

Most research focuses on correction accuracy, but clinical deployment requires:
1. **Speed**: <1 second per slice for real-time feedback
2. **Memory**: Fit on standard hospital workstations
3. **Reliability**: Consistent performance, no GPU required
4. **Simplicity**: Easy integration with existing scanners

Can we design motion correction methods that are both accurate AND clinically deployable?

Target use cases:
- Real-time motion monitoring during scan
- On-scanner immediate feedback
- Low-resource settings
- Retroactive batch processing of large datasets

## Background

- **Field**: Efficient Deep Learning / Edge Deployment
- **Sub-area**: Model compression, neural architecture search, efficient CNNs
- **Key concepts**:
  - FLOPs vs latency tradeoff
  - Model compression: pruning, quantization, distillation
  - Efficient architectures: MobileNet, EfficientNet
  - Knowledge distillation
  - ONNX/TensorRT deployment
- **Related work**:
  - Lightweight image restoration networks
  - Real-time medical image processing
  - Model compression for medical AI
  - Edge deployment of deep learning

## Constraints

- **Compute**: 4x RTX 4090 (for training only)
- **Target deployment**: CPU or entry-level GPU
- **Inference time**: <100ms per image (ideally <50ms)
- **Model size**: <100MB (ideally <50MB)
- **Timeline**: 4-6 months to MICCAI/IPMI
- **Target venue**: MICCAI / TMI

## What I'm Looking For

- [x] New method: efficient motion correction architecture
- [ ] Speed-accuracy Pareto frontier analysis
- [ ] Deployment-ready solution

## Domain Knowledge

### Efficiency Techniques:

1. **Architecture design**:
   - Depthwise separable convolutions
   - Bottleneck structures
   - Efficient attention (linear attention, local attention)
   - Early downsampling, late upsampling

2. **Model compression**:
   - Pruning: remove redundant weights
   - Quantization: INT8 instead of FP32
   - Knowledge distillation: small student learns from large teacher
   - Neural architecture search (NAS)

3. **Implementation optimizations**:
   - ONNX export for cross-platform
   - TensorRT for NVIDIA GPUs
   - OpenVINO for Intel CPUs
   - TensorFlow Lite for mobile/edge

### Speed-Accuracy Tradeoffs:

```
Accuracy
    │
    │    ● High-accuracy (slow)
    │   ╱
    │  ╱  ★ Target (good enough, fast)
    │ ╱
    │● Fast but poor
    └─────────────────► Speed
```

Goal: Find the "knee" of the curve - where speed improvements don't hurt accuracy much.

### Clinical Deployment Considerations:

1. **Integration**:
   - DICOM input/output
   - PACS compatibility
   - Scanner vendor independence

2. **Regulatory**:
   - FDA clearance pathway
   - CE marking for Europe
   - Clinical validation requirements

3. **Operational**:
   - Minimal IT infrastructure
   - Automatic updates
   - Error handling and logging

## Non-Goals

- Maximum accuracy at any cost (need practical speed)
- Methods requiring high-end GPUs
- Complex multi-model ensembles
- Real-time reconstruction (focus on correction only)

## Existing Results

None yet - initial exploration.

## Success Criteria

- Inference <100ms on CPU or entry-level GPU
- Model size <100MB
- Accuracy within 5% of unconstrained method
- Deployment guide included (ONNX/TensorRT)
- Demonstrated on realistic clinical hardware

## Evaluation Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Inference time | <100ms | Average over 100 images |
| Memory footprint | <100MB | Model size on disk |
| FLOPs | <10G | Per image |
| PSNR/SSIM | >95% of baseline | Compared to heavy model |

## Related Work to Review

- "MobileNetV2: Inverted Residuals and Linear Bottlenecks"
- "EfficientNet: Rethinking Model Scaling"
- "Knowledge Distillation: A Survey"
- "Deep Compression: Compressing Deep Neural Networks"
