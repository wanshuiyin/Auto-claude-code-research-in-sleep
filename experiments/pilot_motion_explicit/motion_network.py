"""
Motion Estimation Network for MRI Motion Correction
显式运动场估计网络 - 方向B的核心组件

Architecture: 轻量级Encoder-Decoder + Correlation Volume
参考: RAFT-lite / PWC-Net简化版
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


class MotionEncoder(nn.Module):
    """特征提取编码器"""
    def __init__(self, in_channels=1, feature_dim=64):
        super().__init__()
        self.conv1 = nn.Sequential(
            nn.Conv2d(in_channels, 32, 7, padding=3),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, 3, padding=1),
            nn.ReLU(inplace=True)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.ReLU(inplace=True)
        )
        self.conv3 = nn.Sequential(
            nn.Conv2d(64, feature_dim, 3, stride=2, padding=1),
            nn.ReLU(inplace=True),
            nn.Conv2d(feature_dim, feature_dim, 3, padding=1),
            nn.ReLU(inplace=True)
        )

    def forward(self, x):
        x1 = self.conv1(x)
        x2 = self.conv2(x1)
        x3 = self.conv3(x2)
        return x3, x2, x1


class MotionDecoder(nn.Module):
    """运动场解码器"""
    def __init__(self, feature_dim=64, motion_dim=2):
        super().__init__()
        self.motion_dim = motion_dim

        # 上采样解码
        self.upconv2 = nn.Sequential(
            nn.ConvTranspose2d(feature_dim, 64, 4, stride=2, padding=1),
            nn.ReLU(inplace=True)
        )
        self.conv2 = nn.Sequential(
            nn.Conv2d(128, 64, 3, padding=1),  # 64+64 from skip
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 64, 3, padding=1),
            nn.ReLU(inplace=True)
        )

        self.upconv1 = nn.Sequential(
            nn.ConvTranspose2d(64, 32, 4, stride=2, padding=1),
            nn.ReLU(inplace=True)
        )
        self.conv1 = nn.Sequential(
            nn.Conv2d(64, 32, 3, padding=1),  # 32+32 from skip
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 32, 3, padding=1),
            nn.ReLU(inplace=True)
        )

        # 运动场预测头
        self.motion_head = nn.Conv2d(32, motion_dim, 3, padding=1)

    def forward(self, x3, x2, x1):
        # 上采样到中间分辨率
        up2 = self.upconv2(x3)
        merge2 = torch.cat([up2, x2], dim=1)
        out2 = self.conv2(merge2)

        # 上采样到原始分辨率
        up1 = self.upconv1(out2)
        merge1 = torch.cat([up1, x1], dim=1)
        out1 = self.conv1(merge1)

        # 预测运动场
        motion = self.motion_head(out1)

        return motion


class MotionNetwork(nn.Module):
    """
    显式运动场估计网络

    输入: 带运动伪影的图像 (B, 1, H, W)
    输出: 运动场 φ (B, 2, H, W) - [dx, dy] for each pixel
    """
    def __init__(self, in_channels=1, feature_dim=64):
        super().__init__()
        self.encoder = MotionEncoder(in_channels, feature_dim)
        self.decoder = MotionDecoder(feature_dim, motion_dim=2)

    def forward(self, corrupted_image):
        """
        Args:
            corrupted_image: (B, 1, H, W) 带运动伪影的MRI图像
        Returns:
            motion_field: (B, 2, H, W) 运动场 [dx, dy]
        """
        feat3, feat2, feat1 = self.encoder(corrupted_image)
        motion_field = self.decoder(feat3, feat2, feat1)
        return motion_field

    def warp(self, image, motion_field):
        """
        使用运动场对图像进行变形

        Args:
            image: (B, C, H, W) 需要变形的图像
            motion_field: (B, 2, H, W) 运动场
        Returns:
            warped: (B, C, H, W) 变形后的图像
        """
        B, C, H, W = image.shape

        # 创建归一化网格 [-1, 1]
        grid_y, grid_x = torch.meshgrid(
            torch.linspace(-1, 1, H, device=image.device),
            torch.linspace(-1, 1, W, device=image.device),
            indexing='ij'
        )
        base_grid = torch.stack([grid_x, grid_y], dim=0).unsqueeze(0).repeat(B, 1, 1, 1)

        # 运动场缩放到网格空间
        # motion_field: [dx, dy] in pixels -> normalize to [-1, 1]
        motion_norm = torch.stack([
            motion_field[:, 0] * 2.0 / W,  # dx
            motion_field[:, 1] * 2.0 / H   # dy
        ], dim=1)

        # 应用到网格
        sampling_grid = base_grid + motion_norm
        sampling_grid = sampling_grid.permute(0, 2, 3, 1)  # (B, H, W, 2)

        # 使用grid_sample进行变形
        warped = F.grid_sample(
            image, sampling_grid,
            mode='bilinear', padding_mode='border', align_corners=True
        )

        return warped


def test_motion_network():
    """测试运动场网络"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Testing MotionNetwork on {device}")

    # 创建模型
    model = MotionNetwork(in_channels=1, feature_dim=64).to(device)

    # 测试输入
    B, H, W = 2, 256, 256
    x = torch.randn(B, 1, H, W).to(device)

    # 前向传播
    motion = model(x)
    print(f"Input shape: {x.shape}")
    print(f"Motion field shape: {motion.shape}")
    print(f"Motion range: [{motion.min():.3f}, {motion.max():.3f}]")

    # 测试warp
    warped = model.warp(x, motion)
    print(f"Warped shape: {warped.shape}")

    # 测试梯度
    loss = motion.abs().mean()
    loss.backward()
    print("Gradient backprop: OK")

    # 计算参数量
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {n_params / 1e6:.2f}M")

    return model


if __name__ == "__main__":
    test_motion_network()
