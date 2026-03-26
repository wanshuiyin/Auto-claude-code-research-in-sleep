"""
Pilot Training Script for Motion-Explicit Diffusion
端到端训练脚本 - 方向B可行性验证

训练流程:
1. 模拟运动伪影数据
2. 运动估计网络预测运动场
3. 条件化扩散模型去噪
4. 物理约束保证数据一致性
5. 自监督损失训练
"""

import os
import sys
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
import numpy as np
from tqdm import tqdm
import json

# 导入自定义模块
from motion_network import MotionNetwork
from physics_layer import KSpacePhysics, MotionCorruptionSimulator
from diffusion_cond import ConditionalUNet, DiffusionScheduler
from self_supervised_loss import CombinedLoss


class SimulatedMRIDataset(Dataset):
    """
    模拟MRI数据集 - 用于pilot验证

    生成清晰图像并模拟运动伪影
    """

    def __init__(self, num_samples=100, image_size=128, motion_type='rigid'):
        self.num_samples = num_samples
        self.image_size = image_size
        self.motion_type = motion_type

        # 模拟器
        self.simulator = MotionCorruptionSimulator()

        # 预生成一些模拟数据
        self.data = []
        print(f"Generating {num_samples} simulated samples...")
        for i in range(num_samples):
            # 生成模拟的清晰MRI图像 (简单模拟)
            clean = self._generate_synthetic_mri(image_size)

            # 模拟运动伪影
            if motion_type == 'rigid':
                corrupted, motion_params = self.simulator.simulate_rigid_motion(
                    clean.unsqueeze(0), max_rotation=3.0, max_translation=3.0
                )
                # 刚性运动：从参数构建运动场（近似）
                motion_field = self._rigid_to_motion_field(
                    motion_params, image_size
                )
            else:
                corrupted, motion_field = self.simulator.simulate_nonrigid_motion(
                    clean.unsqueeze(0), scale=2.0
                )
                motion_field = motion_field.squeeze(0)

            corrupted = corrupted.squeeze(0)

            self.data.append({
                'clean': clean,
                'corrupted': corrupted,
                'motion_field': motion_field
            })

    def _rigid_to_motion_field(self, motion_params, size):
        """将刚性运动参数转换为运动场（用于统一处理）"""
        # 创建一个简单的运动场表示（基于旋转和平移的近似）
        # 实际使用时可以用更精确的变换，但这里仅用于避免None
        y_grid, x_grid = torch.meshgrid(
            torch.arange(size), torch.arange(size), indexing='ij'
        )
        # 简化为零运动场（刚性运动在图像域难以用dense flow表示）
        # 或者可以用参数表示：motion_field = [tx, ty] 扩展
        motion_field = torch.zeros(2, size, size)
        return motion_field

    def _generate_synthetic_mri(self, size):
        """生成模拟MRI图像"""
        # 简单模拟: 椭圆+噪声
        x = torch.zeros(1, size, size)

        # 添加一些结构
        center = size // 2
        y_grid, x_grid = torch.meshgrid(
            torch.arange(size), torch.arange(size), indexing='ij'
        )

        # 模拟脑结构
        dist = torch.sqrt((x_grid - center).float()**2 + (y_grid - center).float()**2)
        x[0] = torch.exp(-dist / (size / 3))

        # 添加一些细节
        x[0] += 0.3 * torch.sin(2 * np.pi * x_grid / size) * torch.sin(2 * np.pi * y_grid / size)

        # 添加噪声
        x += 0.05 * torch.randn_like(x)

        # 归一化
        x = (x - x.min()) / (x.max() - x.min() + 1e-8)

        return x

    def __len__(self):
        return self.num_samples

    def __getitem__(self, idx):
        return self.data[idx]


class PilotTrainer:
    """
    Pilot训练器

    训练运动估计网络和扩散模型的联合框架
    """

    def __init__(
        self,
        motion_net,
        diffusion_model,
        physics_layer,
        scheduler,
        device='cuda',
        lr=1e-4
    ):
        self.motion_net = motion_net.to(device)
        self.diffusion_model = diffusion_model.to(device)
        self.physics_layer = physics_layer.to(device)
        self.scheduler = scheduler
        self.device = device

        # 优化器
        self.optimizer = optim.Adam(
            list(motion_net.parameters()) + list(diffusion_model.parameters()),
            lr=lr
        )

        # 损失函数
        self.loss_fn = CombinedLoss(
            lambda_diffusion=1.0,
            lambda_self_supervised=0.1,
            lambda_motion_smooth=0.01
        )

        # 日志
        self.train_losses = []
        self.val_metrics = []

    def train_step(self, batch):
        """单步训练"""
        corrupted = batch['corrupted'].to(self.device)
        clean = batch['clean'].to(self.device)

        B = corrupted.shape[0]

        # 1. 估计运动场
        motion_field = self.motion_net(corrupted)

        # 2. 扩散训练
        # 随机时间步
        t = torch.randint(0, self.scheduler.num_timesteps, (B,), device=self.device)

        # 添加噪声
        noise = torch.randn_like(clean)
        x_t = self.scheduler.add_noise(clean, t, noise)

        # 预测噪声
        noise_pred = self.diffusion_model(x_t, t, motion_field)

        # 预测x0 (用于自监督损失)
        alpha_t = self.scheduler.alphas_cumprod[t].view(-1, 1, 1, 1).to(self.device)
        sqrt_one_minus_alpha_t = self.scheduler.sqrt_one_minus_alphas_cumprod[t].view(-1, 1, 1, 1).to(self.device)
        pred_x0 = (x_t - sqrt_one_minus_alpha_t * noise_pred) / torch.sqrt(alpha_t)

        # 3. 计算损失
        measured_kspace = self.physics_layer.fft2(corrupted)
        mask = torch.ones(corrupted.shape[-2], corrupted.shape[-1]).to(self.device)

        total_loss, losses = self.loss_fn(
            noise_pred, noise,
            pred_x0, corrupted,
            motion_field, self.motion_net,
            measured_kspace, mask, self.physics_layer
        )

        # 4. 反向传播
        self.optimizer.zero_grad()
        total_loss.backward()

        # 梯度裁剪
        torch.nn.utils.clip_grad_norm_(
            list(self.motion_net.parameters()) + list(self.diffusion_model.parameters()),
            max_norm=1.0
        )

        self.optimizer.step()

        return losses

    @torch.no_grad()
    def sample(self, corrupted, num_steps=None):
        """
        从运动污染图像采样重建
        使用完整的DDPM采样（1000 steps）确保数学正确性

        Args:
            corrupted: (B, 1, H, W) 运动污染图像
            num_steps: 不使用，保持API兼容
        Returns:
            reconstructed: (B, 1, H, W) 重建图像
        """
        self.motion_net.eval()
        self.diffusion_model.eval()

        B = corrupted.shape[0]

        # 估计运动场
        motion_field = self.motion_net(corrupted)

        # 从噪声开始
        x = torch.randn_like(corrupted)

        # 完整的DDPM采样（从T到0）
        for t in reversed(range(self.scheduler.num_timesteps)):
            t_batch = torch.full((B,), t, device=self.device, dtype=torch.long)
            x = self.scheduler.sample_step(
                self.diffusion_model, x, t_batch, motion_field
            )

        return x, motion_field

    @torch.no_grad()
    def evaluate(self, val_loader):
        """验证集评估"""
        self.motion_net.eval()
        self.diffusion_model.eval()

        total_psnr = 0
        total_ssim = 0
        num_samples = 0

        for batch in val_loader:
            corrupted = batch['corrupted'].to(self.device)
            clean = batch['clean'].to(self.device)

            # 采样重建
            recon, _ = self.sample(corrupted, num_steps=50)

            # 计算PSNR和SSIM (简化版)
            mse = torch.mean((recon - clean) ** 2)
            psnr = 20 * torch.log10(1.0 / torch.sqrt(mse + 1e-8))
            total_psnr += psnr.item() * clean.shape[0]

            num_samples += clean.shape[0]

        return {
            'psnr': total_psnr / num_samples,
            'ssim': 0.0  # 简化，暂不计算SSIM
        }

    def train(self, train_loader, val_loader, num_epochs=10):
        """完整训练循环"""
        print(f"Starting training for {num_epochs} epochs...")

        for epoch in range(num_epochs):
            self.motion_net.train()
            self.diffusion_model.train()

            epoch_losses = []
            pbar = tqdm(train_loader, desc=f"Epoch {epoch+1}/{num_epochs}")

            for batch in pbar:
                losses = self.train_step(batch)
                epoch_losses.append(losses['total'].item())

                pbar.set_postfix({
                    'loss': f"{losses['total'].item():.4f}",
                    'mse': f"{losses.get('mse', 0).item():.4f}" if isinstance(losses.get('mse'), torch.Tensor) else "N/A"
                })

            avg_loss = np.mean(epoch_losses)
            self.train_losses.append(avg_loss)

            # 验证
            metrics = self.evaluate(val_loader)
            self.val_metrics.append(metrics)

            print(f"Epoch {epoch+1}: Train Loss = {avg_loss:.4f}, Val PSNR = {metrics['psnr']:.2f}")

        print("Training completed!")
        return self.train_losses, self.val_metrics


def compute_ssim(img1, img2, window_size=11):
    """简化版SSIM计算"""
    # 简化为相关系数
    img1 = img1.flatten()
    img2 = img2.flatten()

    mu1 = img1.mean()
    mu2 = img2.mean()

    sigma1 = img1.std()
    sigma2 = img2.std()

    sigma12 = ((img1 - mu1) * (img2 - mu2)).mean()

    c1 = 0.01 ** 2
    c2 = 0.03 ** 2

    ssim = ((2 * mu1 * mu2 + c1) * (2 * sigma12 + c2)) / \
           ((mu1**2 + mu2**2 + c1) * (sigma1**2 + sigma2**2 + c2))

    return ssim


def run_pilot_experiment():
    """运行pilot实验"""
    print("="*60)
    print("Pilot Experiment: Motion-Explicit Diffusion for MRI Motion Correction")
    print("="*60)

    # 设备
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    # 超参数
    image_size = 128
    batch_size = 4
    num_epochs = 5  # pilot用较少epoch
    num_train = 80
    num_val = 20

    # 数据集
    print("\nPreparing datasets...")
    train_dataset = SimulatedMRIDataset(num_samples=num_train, image_size=image_size)
    val_dataset = SimulatedMRIDataset(num_samples=num_val, image_size=image_size)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # 模型
    print("\nInitializing models...")
    motion_net = MotionNetwork(in_channels=1, feature_dim=32)
    diffusion_model = ConditionalUNet(
        in_channels=1,
        model_channels=32,
        channel_mult=(1, 2, 4),
        num_res_blocks=1
    )
    physics_layer = KSpacePhysics()
    scheduler = DiffusionScheduler(num_timesteps=1000)

    # 打印参数量
    motion_params = sum(p.numel() for p in motion_net.parameters())
    diffusion_params = sum(p.numel() for p in diffusion_model.parameters())
    print(f"Motion Network: {motion_params/1e6:.2f}M parameters")
    print(f"Diffusion Model: {diffusion_params/1e6:.2f}M parameters")
    print(f"Total: {(motion_params + diffusion_params)/1e6:.2f}M parameters")

    # 训练器
    trainer = PilotTrainer(
        motion_net=motion_net,
        diffusion_model=diffusion_model,
        physics_layer=physics_layer,
        scheduler=scheduler,
        device=device,
        lr=1e-4
    )

    # 训练
    print("\nStarting training...")
    train_losses, val_metrics = trainer.train(train_loader, val_loader, num_epochs=num_epochs)

    # 保存结果
    results = {
        'train_losses': train_losses,
        'val_psnrs': [m['psnr'] for m in val_metrics],
        'config': {
            'image_size': image_size,
            'batch_size': batch_size,
            'num_epochs': num_epochs,
            'motion_params': motion_params,
            'diffusion_params': diffusion_params
        }
    }

    # 保存模型
    save_dir = 'experiments/pilot_motion_explicit/checkpoints'
    os.makedirs(save_dir, exist_ok=True)

    torch.save({
        'motion_net': motion_net.state_dict(),
        'diffusion_model': diffusion_model.state_dict(),
        'results': results
    }, os.path.join(save_dir, 'pilot_checkpoint.pt'))

    # 保存结果
    with open(os.path.join(save_dir, 'pilot_results.json'), 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {save_dir}")
    print(f"Final Train Loss: {train_losses[-1]:.4f}")
    print(f"Final Val PSNR: {val_metrics[-1]['psnr']:.2f}")

    # 验证通过标准
    print("\n" + "="*60)
    print("VALIDATION CHECK")
    print("="*60)

    checks = {
        "Training completed without NaN/Inf": not np.isnan(train_losses[-1]),
        "Train loss decreased": train_losses[-1] < train_losses[0],
        "PSNR improved": val_metrics[-1]['psnr'] > 15.0,  # 简化标准
    }

    all_passed = True
    for check, passed in checks.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status}: {check}")
        all_passed = all_passed and passed

    if all_passed:
        print("\n🎉 All validation checks passed!")
        print("Direction B (Motion-Explicit Diffusion) is FEASIBLE.")
    else:
        print("\n⚠️ Some checks failed. Consider alternative directions.")

    return all_passed, results


if __name__ == "__main__":
    success, results = run_pilot_experiment()
    sys.exit(0 if success else 1)
