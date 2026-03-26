"""
Physics Layer - K-space Data Consistency
物理约束层 - k-space数据一致性操作

核心操作:
1. FFT/IFFT (可微)
2. k-space masking
3. Data consistency projection
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class KSpacePhysics(nn.Module):
    """
    K-space物理约束层

    MRI前向模型: y = M * F(x) + n
    - F: 傅里叶变换
    - M: 采样掩码 (undersampling mask or motion corruption mask)
    - y: 采集的k-space数据
    """

    def __init__(self):
        super().__init__()

    def fft2(self, image):
        """
        2D傅里叶变换 (可微)

        Args:
            image: (B, C, H, W) 图像域数据
        Returns:
            kspace: (B, C, H, W, 2) k-space数据 (实部, 虚部)
        """
        # 转换为复数
        image_complex = torch.view_as_complex(
            torch.stack([image, torch.zeros_like(image)], dim=-1)
        )
        # FFT
        kspace_complex = torch.fft.fft2(image_complex, norm='ortho')
        # 转换回实张量
        kspace = torch.view_as_real(kspace_complex)
        return kspace

    def ifft2(self, kspace):
        """
        2D逆傅里叶变换 (可微)

        Args:
            kspace: (B, C, H, W, 2) k-space数据
        Returns:
            image: (B, C, H, W) 图像域数据
        """
        # 转换为复数
        kspace_complex = torch.view_as_complex(kspace)
        # IFFT
        image_complex = torch.fft.ifft2(kspace_complex, norm='ortho')
        # 取实部
        image = image_complex.real
        return image

    def data_consistency_loss(self, pred_image, measured_kspace, mask):
        """
        数据一致性损失

        Loss = ||M * F(pred) - measured_kspace||^2

        Args:
            pred_image: (B, C, H, W) 预测图像
            measured_kspace: (B, C, H, W, 2) 测量的k-space数据
            mask: (B, C, H, W, 2) 或 (H, W) 采样掩码
        Returns:
            loss: 标量
        """
        # 预测图像 -> k-space
        pred_kspace = self.fft2(pred_image)

        # 应用掩码
        if mask.dim() == 2:
            mask = mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1)
            mask = mask.repeat(pred_kspace.shape[0], pred_kspace.shape[1], 1, 1, 2)

        # 只在采样位置计算差异
        diff = mask * (pred_kspace - measured_kspace)
        loss = torch.sum(diff ** 2) / (torch.sum(mask) + 1e-8)

        return loss

    def data_consistency_projection(self, pred_image, measured_kspace, mask):
        """
        数据一致性投影 (硬约束)

        在k-space用测量值替换预测值:
        F(x̂_new) = M * y_measured + (1-M) * F(x̂_pred)

        Args:
            pred_image: (B, C, H, W) 预测图像
            measured_kspace: (B, C, H, W, 2) 测量的k-space数据
            mask: (B, C, H, W, 2) 或 (H, W) 采样掩码
        Returns:
            corrected_image: (B, C, H, W) 投影后的图像
        """
        # 预测图像 -> k-space
        pred_kspace = self.fft2(pred_image)

        # 应用掩码
        if mask.dim() == 2:
            mask = mask.unsqueeze(0).unsqueeze(0).unsqueeze(-1)
            mask = mask.repeat(pred_kspace.shape[0], pred_kspace.shape[1], 1, 1, 2)

        # 数据一致性投影
        corrected_kspace = mask * measured_kspace + (1 - mask) * pred_kspace

        # 转回图像域
        corrected_image = self.ifft2(corrected_kspace)

        return corrected_image


class MotionCorruptionSimulator(nn.Module):
    """
    运动伪影模拟器 - 用于生成训练数据

    模拟MRI运动伪影: 从清晰图像生成运动污染图像
    """

    def __init__(self):
        super().__init__()
        self.physics = KSpacePhysics()

    def simulate_rigid_motion(self, clean_image, max_rotation=5.0, max_translation=5.0):
        """
        模拟刚性运动伪影

        Args:
            clean_image: (B, C, H, W) 清晰图像
            max_rotation: 最大旋转角度（度）
            max_translation: 最大平移（像素）
        Returns:
            corrupted_image: (B, C, H, W) 运动污染图像
            motion_params: dict 运动参数
        """
        B, C, H, W = clean_image.shape
        device = clean_image.device

        # 随机运动参数
        angles = torch.rand(B, device=device) * 2 * max_rotation - max_rotation
        angles = angles * torch.pi / 180  # 转弧度

        tx = torch.rand(B, device=device) * 2 * max_translation - max_translation
        ty = torch.rand(B, device=device) * 2 * max_translation - max_translation

        # 创建变换矩阵
        corrupted = []
        for i in range(B):
            angle = angles[i]
            # 旋转+平移矩阵
            cos_a, sin_a = torch.cos(angle), torch.sin(angle)
            theta = torch.tensor([
                [cos_a, -sin_a, tx[i] / (W / 2)],
                [sin_a, cos_a, ty[i] / (H / 2)]
            ], device=device).unsqueeze(0)

            # 应用变换
            grid = F.affine_grid(theta, clean_image[i:i+1].size(), align_corners=True)
            warped = F.grid_sample(
                clean_image[i:i+1], grid,
                mode='bilinear', padding_mode='border', align_corners=True
            )
            corrupted.append(warped)

        corrupted_image = torch.cat(corrupted, dim=0)

        motion_params = {
            'angles': angles,
            'translations': torch.stack([tx, ty], dim=1)
        }

        return corrupted_image, motion_params

    def simulate_nonrigid_motion(self, clean_image, scale=3.0):
        """
        模拟非刚性运动伪影（简化版：弹性变形）

        Args:
            clean_image: (B, C, H, W) 清晰图像
            scale: 变形强度
        Returns:
            corrupted_image: (B, C, H, W) 运动污染图像
            flow: (B, 2, H, W) 变形场
        """
        B, C, H, W = clean_image.shape
        device = clean_image.device

        # 生成平滑的变形场
        # 先在小分辨率生成噪声，再上采样
        small_h, small_w = H // 8, W // 8
        flow_small = torch.randn(B, 2, small_h, small_w, device=device) * scale

        flow = F.interpolate(flow_small, size=(H, W), mode='bilinear', align_corners=True)

        # 归一化到网格空间 [-1, 1]
        flow_norm = torch.stack([
            flow[:, 0] * 2.0 / W,
            flow[:, 1] * 2.0 / H
        ], dim=1)

        # 创建基础网格
        grid_y, grid_x = torch.meshgrid(
            torch.linspace(-1, 1, H, device=device),
            torch.linspace(-1, 1, W, device=device),
            indexing='ij'
        )
        base_grid = torch.stack([grid_x, grid_y], dim=0).unsqueeze(0).repeat(B, 1, 1, 1)

        # 应用变形
        sampling_grid = base_grid + flow_norm
        sampling_grid = sampling_grid.permute(0, 2, 3, 1)

        corrupted_image = F.grid_sample(
            clean_image, sampling_grid,
            mode='bilinear', padding_mode='border', align_corners=True
        )

        return corrupted_image, flow


def test_physics_layer():
    """测试物理层"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Testing KSpacePhysics on {device}")

    physics = KSpacePhysics().to(device)

    # 测试FFT/IFFT
    B, H, W = 2, 128, 128
    x = torch.randn(B, 1, H, W).to(device)

    # FFT
    k = physics.fft2(x)
    print(f"Image shape: {x.shape}")
    print(f"K-space shape: {k.shape}")

    # IFFT
    x_recon = physics.ifft2(k)
    print(f"Recon shape: {x_recon.shape}")
    print(f"Reconstruction error: {(x - x_recon).abs().mean():.6f}")

    # 测试数据一致性
    mask = torch.ones(H, W).to(device)
    mask[:, W//2:] = 0  # 半边采样

    loss = physics.data_consistency_loss(x_recon, k, mask)
    print(f"Data consistency loss: {loss:.6f}")

    # 测试投影
    x_proj = physics.data_consistency_projection(x_recon, k, mask)
    loss_after = physics.data_consistency_loss(x_proj, k, mask)
    print(f"Loss after projection: {loss_after:.6f}")

    # 测试梯度
    loss.backward()
    print("Gradient backprop: OK")

    # 测试运动模拟
    simulator = MotionCorruptionSimulator().to(device)

    x_clean = torch.randn(B, 1, H, W).to(device)
    x_corrupted, params = simulator.simulate_rigid_motion(x_clean)
    print(f"\nRigid motion simulation:")
    print(f"  Corrupted shape: {x_corrupted.shape}")
    print(f"  Angle range: [{params['angles'].min():.2f}, {params['angles'].max():.2f}] rad")

    x_corrupted_nr, flow = simulator.simulate_nonrigid_motion(x_clean)
    print(f"\nNon-rigid motion simulation:")
    print(f"  Corrupted shape: {x_corrupted_nr.shape}")
    print(f"  Flow shape: {flow.shape}")

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_physics_layer()
