"""
Conditional Diffusion Model with Motion Guidance
条件化扩散模型 - 以运动场为条件

基于DDPM，加入运动条件
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import math


class TimeEmbedding(nn.Module):
    """时间步嵌入"""
    def __init__(self, dim):
        super().__init__()
        self.dim = dim

    def forward(self, t):
        """
        Args:
            t: (B,) 时间步
        Returns:
            emb: (B, dim) 时间嵌入
        """
        device = t.device
        half_dim = self.dim // 2
        emb = math.log(10000) / (half_dim - 1)
        emb = torch.exp(torch.arange(half_dim, device=device) * -emb)
        emb = t[:, None] * emb[None, :]
        emb = torch.cat([torch.sin(emb), torch.cos(emb)], dim=-1)
        return emb


class ConditionalUNet(nn.Module):
    """
    条件化U-Net - 接受运动场作为条件

    输入: 噪声图像 + 运动场
    输出: 预测的噪声
    """

    def __init__(
        self,
        in_channels=1,
        model_channels=64,
        out_channels=1,
        num_res_blocks=2,
        attention_resolutions=[8, 16],
        dropout=0.0,
        channel_mult=(1, 2, 4, 8),
        motion_condition_dim=2  # [dx, dy]
    ):
        super().__init__()

        self.in_channels = in_channels
        self.model_channels = model_channels
        self.out_channels = out_channels
        self.num_res_blocks = num_res_blocks

        # 时间嵌入
        time_embed_dim = model_channels * 4
        self.time_embed = nn.Sequential(
            TimeEmbedding(model_channels),
            nn.Linear(model_channels, time_embed_dim),
            nn.SiLU(),
            nn.Linear(time_embed_dim, time_embed_dim),
        )

        # 输入投影 (图像 + 运动场)
        self.input_proj = nn.Conv2d(
            in_channels + motion_condition_dim,
            model_channels,
            3,
            padding=1
        )

        # 下采样路径
        self.down_blocks = nn.ModuleList()
        ch = model_channels
        input_block_chans = [ch]

        for level, mult in enumerate(channel_mult):
            for _ in range(num_res_blocks):
                self.down_blocks.append(ResBlock(ch, mult * model_channels, time_embed_dim, dropout))
                ch = mult * model_channels
                input_block_chans.append(ch)

            if level != len(channel_mult) - 1:
                self.down_blocks.append(Downsample(ch))
                input_block_chans.append(ch)

        # 中间层
        self.middle_block = nn.ModuleList([
            ResBlock(ch, ch, time_embed_dim, dropout),
            ResBlock(ch, ch, time_embed_dim, dropout),
        ])

        # 上采样路径
        self.up_blocks = nn.ModuleList()

        for level, mult in list(enumerate(channel_mult))[::-1]:
            for i in range(num_res_blocks + 1):
                ich = input_block_chans.pop()
                self.up_blocks.append(ResBlock(ch + ich, mult * model_channels, time_embed_dim, dropout))
                ch = mult * model_channels

            if level != 0:
                self.up_blocks.append(Upsample(ch))

        # 输出
        self.out = nn.Sequential(
            nn.GroupNorm(32, ch),
            nn.SiLU(),
            nn.Conv2d(ch, out_channels, 3, padding=1),
        )

    def forward(self, x, t, motion_field):
        """
        Args:
            x: (B, C, H, W) 噪声图像
            t: (B,) 时间步
            motion_field: (B, 2, H, W) 运动场
        Returns:
            noise_pred: (B, C, H, W) 预测的噪声
        """
        # 时间嵌入
        t_emb = self.time_embed(t)

        # 拼接图像和运动场作为输入
        x_cond = torch.cat([x, motion_field], dim=1)
        h = self.input_proj(x_cond)

        # 下采样
        hs = [h]
        for module in self.down_blocks:
            if isinstance(module, ResBlock):
                h = module(h, t_emb)
            elif isinstance(module, (Downsample, Upsample)):
                h = module(h)
            else:
                h = module(h)
            hs.append(h)

        # 中间
        for module in self.middle_block:
            h = module(h, t_emb)

        # 上采样
        for module in self.up_blocks:
            if isinstance(module, ResBlock):
                h = torch.cat([h, hs.pop()], dim=1)
                h = module(h, t_emb)
            elif isinstance(module, (Downsample, Upsample)):
                h = module(h)
            else:
                h = module(h)

        return self.out(h)


class ResBlock(nn.Module):
    """残差块"""
    def __init__(self, in_ch, out_ch, time_emb_dim, dropout):
        super().__init__()
        self.in_ch = in_ch
        self.out_ch = out_ch

        self.norm1 = nn.GroupNorm(32, in_ch)
        self.conv1 = nn.Conv2d(in_ch, out_ch, 3, padding=1)

        self.time_emb_proj = nn.Linear(time_emb_dim, out_ch)

        self.norm2 = nn.GroupNorm(32, out_ch)
        self.dropout = nn.Dropout(dropout)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)

        if in_ch != out_ch:
            self.skip = nn.Conv2d(in_ch, out_ch, 1)
        else:
            self.skip = nn.Identity()

    def forward(self, x, t_emb):
        h = self.norm1(x)
        h = F.silu(h)
        h = self.conv1(h)

        # 加入时间嵌入
        h = h + self.time_emb_proj(F.silu(t_emb))[:, :, None, None]

        h = self.norm2(h)
        h = F.silu(h)
        h = self.dropout(h)
        h = self.conv2(h)

        return h + self.skip(x)


class Downsample(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, 3, stride=2, padding=1)

    def forward(self, x):
        return self.conv(x)


class Upsample(nn.Module):
    def __init__(self, channels):
        super().__init__()
        self.conv = nn.Conv2d(channels, channels, 3, padding=1)

    def forward(self, x):
        x = F.interpolate(x, scale_factor=2, mode='nearest')
        return self.conv(x)


class DiffusionScheduler(nn.Module):
    """
    DDPM调度器 - 使用register_buffer确保设备一致性
    """
    def __init__(self, num_timesteps=1000, beta_start=1e-4, beta_end=0.02):
        super().__init__()
        self.num_timesteps = num_timesteps

        # 线性调度
        betas = torch.linspace(beta_start, beta_end, num_timesteps)
        alphas = 1.0 - betas
        alphas_cumprod = torch.cumprod(alphas, dim=0)
        alphas_cumprod_prev = torch.cat([torch.tensor([1.0]), alphas_cumprod[:-1]])

        # 使用register_buffer确保随模型移动设备
        self.register_buffer('betas', betas)
        self.register_buffer('alphas', alphas)
        self.register_buffer('alphas_cumprod', alphas_cumprod)
        self.register_buffer('alphas_cumprod_prev', alphas_cumprod_prev)

        # 预计算
        self.register_buffer('sqrt_alphas_cumprod', torch.sqrt(alphas_cumprod))
        self.register_buffer('sqrt_one_minus_alphas_cumprod', torch.sqrt(1.0 - alphas_cumprod))
        self.register_buffer('sqrt_recip_alphas', torch.sqrt(1.0 / alphas))

        # 后验方差
        posterior_variance = betas * (1.0 - alphas_cumprod_prev) / (1.0 - alphas_cumprod)
        self.register_buffer('posterior_variance', posterior_variance)

    def add_noise(self, x0, t, noise=None):
        """
        前向扩散: q(x_t | x_0)
        """
        if noise is None:
            noise = torch.randn_like(x0)

        sqrt_alpha = self.sqrt_alphas_cumprod[t].view(-1, 1, 1, 1)
        sqrt_one_minus_alpha = self.sqrt_one_minus_alphas_cumprod[t].view(-1, 1, 1, 1)

        return sqrt_alpha * x0 + sqrt_one_minus_alpha * noise

    def sample_step(self, model, x_t, t, motion_field, physics_layer=None, measured_kspace=None, mask=None):
        """
        反向扩散单步: p(x_{t-1} | x_t)

        Args:
            model: 去噪模型
            x_t: 当前噪声图像
            t: 时间步
            motion_field: 运动场条件
            physics_layer: 物理层（可选，用于数据一致性投影）
            measured_kspace: 测量的k-space（用于投影）
            mask: 采样掩码（用于投影）
        """
        betas_t = self.betas[t].view(-1, 1, 1, 1)
        sqrt_one_minus_alpha_t = self.sqrt_one_minus_alphas_cumprod[t].view(-1, 1, 1, 1)
        sqrt_recip_alpha_t = self.sqrt_recip_alphas[t].view(-1, 1, 1, 1)

        # 预测噪声
        noise_pred = model(x_t, t, motion_field)

        # 预测x0
        pred_x0 = (x_t - sqrt_one_minus_alpha_t * noise_pred) / sqrt_recip_alpha_t

        # 计算x_{t-1}的均值
        model_mean = sqrt_recip_alpha_t * (x_t - betas_t / sqrt_one_minus_alpha_t * noise_pred)

        if t[0] == 0:
            return model_mean

        # 添加噪声
        posterior_variance_t = self.posterior_variance[t].view(-1, 1, 1, 1)
        noise = torch.randn_like(x_t)
        x_t_minus_1 = model_mean + torch.sqrt(posterior_variance_t) * noise

        # 可选：数据一致性投影
        if physics_layer is not None and measured_kspace is not None and mask is not None:
            x_t_minus_1 = physics_layer.data_consistency_projection(x_t_minus_1, measured_kspace, mask)

        return x_t_minus_1


def test_conditional_diffusion():
    """测试条件化扩散模型"""
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Testing Conditional Diffusion on {device}")

    # 创建模型
    model = ConditionalUNet(
        in_channels=1,
        model_channels=32,
        channel_mult=(1, 2, 4),
        num_res_blocks=1
    ).to(device)

    # 测试输入
    B, H, W = 2, 128, 128
    x = torch.randn(B, 1, H, W).to(device)
    t = torch.randint(0, 1000, (B,)).to(device)
    motion = torch.randn(B, 2, H, W).to(device)

    # 前向传播
    noise_pred = model(x, t, motion)
    print(f"Input shape: {x.shape}")
    print(f"Motion shape: {motion.shape}")
    print(f"Noise pred shape: {noise_pred.shape}")

    # 测试调度器
    scheduler = DiffusionScheduler(num_timesteps=1000)
    x_noisy = scheduler.add_noise(x, t)
    print(f"Noisy shape: {x_noisy.shape}")

    # 测试采样
    x_next = scheduler.sample_step(model, x_noisy, t, motion)
    print(f"Sampled shape: {x_next.shape}")

    # 测试梯度
    loss = noise_pred.abs().mean()
    loss.backward()
    print("Gradient backprop: OK")

    # 参数量
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Total parameters: {n_params / 1e6:.2f}M")

    print("\nAll tests passed!")


if __name__ == "__main__":
    test_conditional_diffusion()
