# 无重叠方案与 Dual Tessellation 性能开销归因

## 结论

原固定规模实验中约 12% 的吞吐差距，主要来自输出几何而不是单个 CUDA block 变慢：

- 基线每 block 产生 `32x64=2048` 个有效输出；
- 无重叠方案每 block 产生 `32x56=1792` 个有效输出；
- 两者每 block 都执行 8 warps、每 warp 4 个 accumulator tile、每 tile 13+13 次 FP64 WMMA；
- 覆盖同一输出域时，无重叠方案需要 `64/56=8/7` 倍 blocks；
- 若单 block 成本相同，理想吞吐比恰为 `56/64=7/8=0.875`。

正式实验测得的吞吐比为 `0.880847` 与 `0.874990`，几乎贴合 `0.875`。进一步把 grid 固定为完全相同的 7168 blocks 后，无重叠方案的单 block 成本比为 `0.995978`，即反而快约 0.4%。因此，“多执行 1/7 blocks”足以解释观察到的性能差距。

## 等 block 探针

探针固定 `height=2048`、`grid.x=64`、`grid.y=112`，两边均启动 7168 blocks，每 block 256 threads。执行 20 次预热与 21 对 AB/BA 样本；单窗口仍控制在 100--300 ms。

| 指标 | 基线 | 无重叠方案 |
| --- | ---: | ---: |
| blocks | 7168 | 7168 |
| 中位单次 kernel 时间 | 11.963977 ms | 11.915852 ms |
| 无重叠/基线单 block 成本 | 1.000000 | 0.995978 |
| 成对 bootstrap 95% CI | - | [0.995762, 0.996104] |

正式同域结果按 block 数归一化后，无重叠/基线单 block 成本在 `1024x7168` 为 `0.993362`，在 `2048x7168` 为 `1.000012`。三个估计共同把单 block 成本限制在约 `0.993--1.000`，远小于 block 数量的 `1.142857` 倍差异。

## 静态工作量账本

以下是源代码语义和 SASS 中 26 条 `DMMA.8x8x4` 静态指令推导的工作量，不等同于硬件 transaction 计数。

| 每 block 指标 | 基线 | 无重叠方案 | 影响 |
| --- | ---: | ---: | --- |
| 有效输出 | 2048 | 1792 | 无重叠少 12.5% |
| 输入元素 | 2660 | 2394 | 无重叠每 block 少 10.0% |
| warp-level 动态 DMMA | 832 | 832 | 每 block 完全相同 |
| 寄存器/线程 | 76 | 76 | 相同 |
| 静态共享内存 | 34368 B | 23424 B | 无重叠少 31.84% |
| 理论活跃 blocks/SM | 2 | 3 | 无重叠多 50% |
| 理论活跃 warps/SM | 16 | 24 | 33.3% 对 50.0% warp occupancy |
| local memory | 0 B | 0 B | 相同 |

同一输出域下，无重叠方案的 blocks 和动态 DMMA 总量都增加 `14.2857%`。以 `2048x7168` 为例，blocks 从 7168 增至 8192，推导的 warp-level DMMA 从 5,963,776 增至 6,815,744。

虽然无重叠方案每 block 读取的输入更少，但按有效输出归一化，输入元素由 `1.29883` 增至 `1.33594` 个/输出，增加 `2.857%`。这是 block 边界 halo 被更多 blocks 重复承担的结果。

## 输出筛选与共享内存

基线通过 `wmma::store_matrix_sync` 直接把每个 8x8 accumulator 写入全局输出。无重叠方案必须丢弃每八个候选中的第八列，因此先把完整 8x8 accumulator 写入共享内存，再读出每行前七个值并写入全局内存。每 block 因此额外包含：

- 2048 个 double 的 accumulator 共享写入；
- 1792 个 double 的筛选共享读取；
- 合计 3840 个 double 级共享访问。

若把显式输入 staging、WMMA 输入读取和输出 staging 全部按源代码元素数估算，共享访问从基线约 31,944 doubles/block 增至无重叠约 32,877 doubles/block，即每 block 约增加 2.92%；按有效输出归一化约增加 17.62%。实际 shared-memory transactions、bank conflicts 与 cache 命中不能由这些语义计数直接推出。

资源探针表明，共享内存容量下降带来的 occupancy 收益，以及每 block 输入减少，足以在实测中抵消输出筛选的额外工作，使无重叠方案的单 block 成本没有增加。但这些收益不能抵消同域计算所需的额外 1/7 blocks。

## 能与不能下的结论

可以确认：

1. 约 12% 的总吞吐差距由 56/64 有效输出几何主导；
2. 两 kernel 单 block 成本基本相同，无重叠方案没有隐藏的约 12% 单块退化；
3. 无重叠方案确实降低共享内存占用并提高理论 occupancy；
4. 输出筛选增加共享内存路径，但其净影响被其他收益抵消。

目前不能精确声称：共享 bank conflict、L1/L2 命中率、DRAM transactions 或 Tensor Core active cycles 分别贡献多少。Nsight Compute 2025.2.1 已安装，但当前系统对普通用户关闭 NVIDIA 性能计数器，返回 `ERR_NVGPUCTRPERM`。本次没有修改 NVIDIA 控制面板或系统权限。

原始证据为 `resource-result.json` 和 `equal-block-result.json`，可分别由 `scripts/run_resource_probe.py` 与 `scripts/run_equal_block_probe.py` 重建。
