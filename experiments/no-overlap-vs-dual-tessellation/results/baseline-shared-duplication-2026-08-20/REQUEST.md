# 原始请求

> 当前 stride=7 无重叠方案先停止性能优化。完成已有诊断并归档即可。下一步不要继续尝试通过微调弥补 7/8 有效输出率。
>
> 请转而分析基线 ConvStencil kernel 中 shared memory 的物理数据重复。保持基线的输出推进方式、block 数、每 block 2048 个有效输出和每 block 832 条 DMMA 完全不变。
>
> 首先只做静态分析：为 shared memory 中每个有效元素追踪其对应的原始 input index，统计相同 input index 在 shared memory 中的重复副本，区分 A/B 重复、相邻 tile 重复、padding 和其他来源。判断这些重复副本中哪些可以通过共享同一物理地址、修改 load 起点/stride 等方式消除，而不改变 WMMA 数量和输出覆盖。
>
> 给出：
>
> 1. 当前 35,392 B shared memory 的组成；
> 2. 真正重复输入数据占多少；
> 3. 在保持当前计算结构完全不变时，理论最小 shared-memory footprint；
> 4. 直接 alias 是否满足现有 FP64 WMMA load 的布局、stride、alignment 要求；
> 5. 如果不能直接 alias，是否可以采用“紧凑 source buffer + 小型临时 WMMA fragment staging”的方式。
>
> 先不要大规模实现。先给出地址映射和可行性结论，再决定是否写 compact-layout prototype。

