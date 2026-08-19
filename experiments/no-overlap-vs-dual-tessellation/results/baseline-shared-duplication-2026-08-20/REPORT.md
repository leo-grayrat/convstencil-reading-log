# ConvStencil 基线 shared-memory 输入重复静态分析

## 范围

本分析只追踪原始 `k=7` ConvStencil 基线 kernel 的 shared-memory 地址映射。没有实现 compact source、alias 或 fragment staging，也没有启动 GPU 测试。

## 地址映射

令 block 的原始输入索引为：

```text
I(r, c) = begin + r * leading_dimension + c
0 <= r < 38, 0 <= c < 70
```

对 `g = 0..7`、`j = 0..6`：

```text
A[g, r, j] = I(r, 8*g + j)
B[g, r, j] = I(r, 8*g + 7 + j)
shared_offset(g, r, j) = g*268 + 7*r + j
```

因此 `g = 0..6, j = 1..6` 时：

```text
B[g, r, j] = A[g+1, r, j-1]
```

A/B 重复和相邻 tile 的 6 列重叠是同一批数据，不能相加计数。七个相邻边界各重复 `6*38=228` 个输入，总计 `7*228=1,596` 个第二副本。

## 35,392 B 的组成

| 类别 | double 数 | 字节 |
| --- | ---: | ---: |
| 唯一有效输入 | 2,660 | 21,280 B |
| 有效输入的第二副本 | 1,596 | 12,768 B |
| 两个 sentinel 槽 | 2 | 16 B |
| group 内未使用 padding | 30 | 240 B |
| plane 尾部 guard/alignment | 8 | 64 B |
| 源码显式 shared memory | 4,296 | 34,368 B |
| 当前 cubin 中 ptxas 附加空间 | — | 1,024 B |
| 资源报告总量 | — | 35,392 B |

`cudaFuncGetAttributes` 和 PTX 显式数组均给出 34,368 B；当前 cubin 的函数 `.nv.shared` section 多出固定 1,024 B。该空间不是输入副本。

真正可通过唯一化输入索引回收的是 1,596 个第二副本，即 **12,768 B**。它占有效输入槽位的 37.5%，占 35,392 B 资源报告的约 36.1%。除 A/B（相邻 tile）重叠外，没有第三类有效输入重复。

## 下限与可行性

- 只考虑唯一输入信息的下限：`2,660 doubles = 21,280 B`。
- 保持八个 warp 并发，并使用每 warp 一个 `8x4` FP64 临时 tile 时：`21,280 + 8*32*8 = 23,328 B` 显式 shared memory。
- 若 ptxas 仍增加相同 1,024 B，资源报告预计约为 24,352 B；该数必须由未来 prototype 编译确认。

现有两 plane 不能整体直接 alias。`B_base = A_base + 267 doubles` 虽能对齐每个七元素小段中的六个重复值，却会把每段的 `j=0` 错误映射到上一行的 `j=6`。此外，416 个输入 fragment load 中有 192 个让连续四个 K 元素跨七元素边界；唯一的 `38x70` source 无法把这些 fragment 直接表示成连续的 row-major `8x4` 矩阵。

CUDA C++ `load_matrix_sync` 还要求 `mptr` 为 256-bit 对齐。现有布局即使假定 plane 基址为 32 B 对齐，也只有 104/416 个起点满足该对齐。现有编译器把 load 降低成标量 shared loads 并不构成新 alias 布局满足 API 契约的证明。

## 未实施建议

“唯一输入 source + 每 warp 一个对齐的 `8x4` staging tile”在地址和 WMMA 形状上可行，而且不必改变每 block 2,048 个输出和 832 条 DMMA。但它会增加 shared-to-shared 重排和 warp 同步，不能由静态 footprint 推断性能收益。

按后续实验要求，本方案在本分支上暂不实现。
