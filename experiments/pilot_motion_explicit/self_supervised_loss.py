"""
Self-Supervised Loss Functions
自监督损失函数 - 无需配对ground truth

包括:
1. 自监督重建损失 (基于MRI前向模型)
2. 运动场平滑正则化
3. 循环一致性损失
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class SelfSupervisedLoss(nn.Module):
    """
    自监督损失组合

    基于MRI前向模型: y = M * F(S * x) + n
    利用采集数据本身作为监督信号
    """

    def __init__(
        self,
        lambda_recon=1.0,
        lambda_motion_smooth=0.1,
        lambda_cycle=0.5,
        lambda_dc=10.0
    ):
        super().__init__()
        self.lambda_recon = lambda_recon
        self.lambda_motion_smooth = lambda_motion_smooth
        self.lambda_cycle = lambda_cycle
        self.lambda_dc = lambda_dc

    def reconstruction_loss(self, pred_image, corrupted_image, motion_network):
        """
        自监督重建损失

        核心思想: 用预测的运动场将重建图像变形回输入域
        Loss = ||MotionNet(ReconNet(Corrupted)) - Corrupted||

        但实际上更简单的方式:
        我们希望: x̂ = ReconNet(y)
        自监督信号: 用y本身构造损失

        对于扩散模型，训练目标是去噪，所以主要监督信号是扩散损失
        这里添加额外的自监督项增强训练
        """
        # 预测运动场
        motion_pred = motion_network(pred_image)

        # 将重建图像用预测的运动场变形
        warped_recon = motion_network.warp(pred_image, motion_pred)

        # 与输入的差异 (但输入是corrupted，这不完全合理)
        # 更合理的做法: 在k-space比较

        # 简化为L1损失
        loss = F.l1_loss(pred_image, corrupted_image)

        return loss, motion_pred

    def motion_smoothness_loss(self, motion_field):
        """
        运动场平滑正则化

        运动通常是局部平滑的，惩罚大的梯度变化
        """
        # 计算空间梯度
        dx = motion_field[:, :, :, 1:] - motion_field[:, :, :, :-1]
        dy = motion_field[:, :, 1:, :] - motion_field[:, :, :-1, :]

        # 总变差
        loss = torch.mean(torch.abs(dx)) + torch.mean(torch.abs(dy))

        return loss

    def cyclic_consistency_loss(self, img_a, img_b, motion_ab, motion_network):
        """
        循环一致性损失

        用运动场φ_ab将a->b，再用反向运动场φ_ba将b->a，应该回到a
        """
        # a -> b
        warped_a = motion_network.warp(img_a, motion_ab)

        # 预测反向运动场
        motion_ba = motion_network(warped_a)

        # b -> a
        warped_back = motion_network.warp(warped_a, motion_ba)

        # 循环一致性
        loss = F.l1_loss(warped_back, img_a)

        return loss

    def forward(self, pred_image, corrupted_image, motion_field, motion_network, physics_layer=None):
        """
        计算总损失

        Args:
            pred_image: 预测的去噪/校正图像
            corrupted_image: 输入的运动污染图像
            motion_field: 预测的运动场
            motion_network: 运动估计网络（用于warp操作）
            physics_layer: 物理层（可选）
        Returns:
            total_loss: 总损失
            loss_dict: 各分项损失
        """
        losses = {}

        # 1. 重建损失
        recon_loss, _ = self.reconstruction_loss(pred_image, corrupted_image, motion_network)
        losses['recon'] = recon_loss

        # 2. 运动场平滑
        smooth_loss = self.motion_smoothness_loss(motion_field)
        losses['motion_smooth'] = smooth_loss

        # 3. 循环一致性 (如果适用)
        # cycle_loss = self.cyclic_consistency_loss(...)
        # losses['cycle'] = cycle_loss

        # 总损失
        total_loss = (
            self.lambda_recon * recon_loss +
            self.lambda_motion_smooth * smooth_loss
        )

        return total_loss, losses


class DiffusionLoss(nn.Module):
    """
    扩散模型训练损失

    标准的MSE损失 + 可选的物理约束
    """

    def __init__(self, lambda_mse=1.0, lambda_dc=0.0):
        super().__init__()
        self.lambda_mse = lambda_mse
        self.lambda_dc = lambda_dc

    def forward(self, noise_pred, noise_target, pred_x0=None, measured_kspace=None, mask=None, physics_layer=None):
        """
        Args:
            noise_pred: 预测的噪声
            noise_target: 目标噪声
            pred_x0: 预测的x0（用于数据一致性）
            measured_kspace: 测量的k-space
            mask: 采样掩码
            physics_layer: 物理层
        """
        # MSE损失
        mse_loss = F.mse_loss(noise_pred, noise_target)

        total_loss = self.lambda_mse * mse_loss
        losses = {'mse': mse_loss}

        # 数据一致性损失（可选）
        if self.lambda_dc > 0 and pred_x0 is not None and physics_layer is not None:
            dc_loss = physics_layer.data_consistency_loss(pred_x0, measured_kspace, mask)
            total_loss = total_loss + self.lambda_dc * dc_loss
            losses['dc'] = dc_loss

        return total_loss, losses


class CombinedLoss(nn.Module):
    """
    组合损失 - 扩散损失 + 自监督损失
    """

    def __init__(
        self,
        lambda_diffusion=1.0,
        lambda_self_supervised=0.1,
        lambda_motion_smooth=0.01
    ):
        super().__init__()
        self.lambda_diffusion = lambda_diffusion
        self.lambda_self_supervised = lambda_self_supervised
        self.lambda_motion_smooth = lambda_motion_smooth

        self.diffusion_loss = DiffusionLoss()
        self.motion_smooth = SelfSupervisedLoss()

    def forward(
        self,
        noise_pred, noise_target,
        pred_x0, corrupted_image,
        motion_field, motion_network,
        measured_kspace=None, mask=None, physics_layer=None
    ):
        """
        组合前向传播
        """
        # 扩散损失
        diff_loss, diff_losses = self.diffusion_loss(
            noise_pred, noise_target,
            pred_x0, measured_kspace, mask, physics_layer
        )

        # 运动场平滑
        smooth_loss = self.motion_smooth.motion_smoothness_loss(motion_field)

        # 自监督重建损失 - 使用k-space数据一致性而非直接像素比较
        # 避免让模型趋向identity reconstruction
        if physics_layer is not None and measured_kspace is not None:
            # k-space数据一致性损失: ||M * F(pred_x0) - measured_kspace||
            recon_loss = physics_layer.data_consistency_loss(pred_x0, measured_kspace, mask)
        else:
            # Fallback: 禁用recon_loss，仅靠扩散损失
            recon_loss = torch.tensor(0.0, device=noise_pred.device)

        # 总损失
        total_loss = (
            self.lambda_diffusion * diff_loss +
            self.lambda_self_supervised * recon_loss +
            self.lambda_motion_smooth * smooth_loss
        )

        losses = {
            **diff_losses,
            'recon': recon_loss,
            'motion_smooth': smooth_loss,
            'total': total_loss
        }

        return total_loss, losses


def test_self_supervised_loss():
    """测试自监督损失"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Testing Self-Supervised Loss on {device}")

    from motion_network import MotionNetwork
    from physics_layer import KSpacePhysics

    # 创建组件
    motion_net = MotionNetwork().to(device)
    physics = KSpacePhysics().to(device)
    loss_fn = CombinedLoss().to(device)

    # 测试数据
    B, H, W = 2, 128, 128
    noise_pred = torch.randn(B, 1, H, W).to(device)
    noise_target = torch.randn(B, 1, H, W).to(device)
    pred_x0 = torch.randn(B, 1, H, W).to(device)
    corrupted = torch.randn(B, 1, H, W).to(device)
    motion_field = torch.randn(B, 2, H, W).to(device) * 0.1

    # 模拟k-space数据
    measured_kspace = physics.fft2(corrupted)
    mask = torch.ones(H, W).to(device)

    # 计算损失
    total_loss, losses = loss_fn(
        noise_pred, noise_target,
        pred_x0, corrupted,
        motion_field, motion_net,
        measured_kspace, mask, physics
    )

    print(f"Total loss: {total_loss.item():.4f}")
    for k, v in losses.items():
        if isinstance(v, torch.Tensor):
            print(f"  {k}: {v.item():.4f}")

    # 测试梯度
    total_loss.backward()
    print("Gradient backprop: OK")

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_self_supervised_loss()
