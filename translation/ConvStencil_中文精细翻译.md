# ConvStencil：将模板计算转换为 Tensor Core 上的矩阵乘法

**原题：** *ConvStencil: Transform Stencil Computation to Matrix Multiplication on Tensor Cores*  
**会议：** PPoPP 2024  
**作者：** Yuetao Chen, Kun Li, Yuhao Wang, Donglin Bai, Lei Wang, Lingxiao Ma, Liang Yuan, Yunquan Zhang, Ting Cao, Mao Yang

> 翻译说明：本文按原论文结构进行精细翻译。保留原有术语、章节编号、公式编号、表格和图注；不转录图中内部文字与图形内容。参考文献题录不逐条翻译。  
> 术语处理：stencil 统一译为“模板计算”或简称“stencil”；Tensor Core Unit 译为“Tensor Core 单元（TCU）”；matrix multiplication 译为“矩阵乘法（MM）”；bank conflict 译为“存储体冲突”；warp divergence 译为“warp 分歧”。

---

## 摘要

Tensor Core 单元（Tensor Core Unit, TCU）正越来越多地被集成到现代高性能处理器中，以提升矩阵乘法的性能。然而，由于这类硬件单元的功能高度专门化，其用于提升其他关键科学计算操作——例如模板计算（stencil computation）——的潜力仍未得到充分挖掘。

本文提出 **ConvStencil**，一种新的 stencil 计算系统，用于高效地将 stencil 计算转换为 Tensor Core 上的矩阵乘法。我们首先为 ConvStencil 建立性能模型，用于指导 TCU 上的算法设计与优化。基于这一模型，我们提出三项技术：

1. 使用 **stencil2row** 方法进行节省内存的布局变换；
2. 通过 **Dual Tessellation（双重镶嵌）** 与 **kernel fusion（核融合）** 实现计算密集化的计算适配；
3. 使用 **Lookup Table（查找表）** 与 **Dirty Bits Padding（脏位填充）** 进行面向性能的冲突消除。

ConvStencil 的性能优于其他 stencil 优化框架，相比 AMOS、cuDNN、Brick、DRStencil 和 TCStencil 等方案获得了显著加速。通过将 stencil 计算转换到 Tensor Core 上，ConvStencil 有望提升多种科学与工程应用的性能。

**CCS 概念：**

- Computing methodologies → Parallel algorithms
- Computer systems organization → Parallel architectures

**关键词：** Stencil Computation，Convolution，Matrix Multiplication，Tensor Cores

---

# 1 引言

随着深度学习模型日益普及，其主要计算特征是矩阵乘法（Matrix Multiplication, MM），已有处理器与新兴处理器都越来越多地集成专门用于加速矩阵乘法的计算单元。这类专用单元被称为 Tensor Core Unit（TCU），例如 NVIDIA GPU 中的 Tensor Core，它们能够为基于矩阵乘法的深度学习模型提供显著的性能加速。

虽然 Tensor Core 能够提供很高的性能，但必须注意，高性能计算（HPC）领域中的计算模式远比深度学习更加多样和复杂，其中大多数都很难直接表示为矩阵乘法。Berkeley View 将 stencil 视为七类对性能至关重要的计算模式之一，而 stencil 正是这类难以直接映射到矩阵乘法的典型代表。

Stencil 包含一种预定义计算模式：在时间维度上迭代地更新一个 \(d\) 维空间网格中的每个点。某一点在时刻 \(t\) 的值，是它自身及其邻域点在前一时刻 \(t-1\) 的加权和。Stencil 是科学与工程计算中最重要的计算核心之一，被广泛用于流体动力学、地球建模以及天气模拟等领域。

目前，只有少量研究探索了如何使用 Tensor Core 执行非矩阵乘法操作。早期工作已经在 Tensor Core 上实现了简单的 reduction 与 scan 原语，这是扩大 Tensor Core 可表达非 MM 操作范围的最早尝试之一。随后，更近期的 TCStencil 尝试将 Tensor Core 用于 stencil 这类更加复杂的计算模式。

然而，TCStencil 存在两个主要问题：算法通用性较差，以及 Tensor Core 利用率较低。

一方面，TCStencil 被限制在 FP16 Tensor Core 上的对称矩阵乘法，即参与乘法的矩阵具有相同形状；而大多数 stencil 计算都需要 FP64 精度，并且 FP64 Tensor Core 只支持特定形式的非对称矩阵乘法。

另一方面，TCStencil 中存在全局内存的非合并访问，以及共享内存中的 bank conflict，这使得 Tensor Core 的计算能力无法得到充分发挥。

据我们所知，目前还没有其他工作能够有效、实用地将 stencil 计算适配到 Tensor Core 上。

本文提出一种新的 stencil 计算系统 **ConvStencil**，旨在高效地将 stencil 计算转换为 Tensor Core 上的矩阵乘法。

ConvStencil 的设计基于一个关键观察：HPC 中的 stencil 与深度学习中的 convolution 在计算模式上具有相似性。两者都会使用一个 stencil kernel（或 convolution kernel）形成滑动窗口，并对输入矩阵窗口中的数据进行加权计算。

为了在 Tensor Core 上高效支持卷积，基于 GEMM 的卷积通常使用 **im2row(col)** 方法：将输入与 filter 均转换为矩阵，从而把卷积表示为矩阵乘法。

由此，我们得到 ConvStencil 的核心想法：

> 既然 stencil 与 convolution 的计算模式如此相似，为什么不能借助 im2row 机制，在 stencil 计算与 Tensor Core 之间建立一座桥梁？

然而，由于 stencil 与 convolution 在算法细节上存在关键差异，这一思路并非唾手可得，仍然需要解决若干重要技术挑战。

首先，将 im2row 应用于 convolution，可以把卷积转换成矩阵乘法。但对于 stencil 而言，每次迭代中 stencil kernel 的数量和 channel 数量都为 1，因此转换后实际得到的是**矩阵—向量乘法**。这可能带来严重的内存膨胀，同时导致 Tensor Core 利用率很低。

其次，FP64 Tensor Core 只支持一种特殊的非对称小矩阵乘法形式，因此如何在这一限制下高效地完成算法适配也是一个挑战。

此外，在具体算法实现与硬件设计之间还可能产生多种性能冲突，例如 warp divergence 与 bank conflict，从而导致性能显著下降。

为解决以上问题，ConvStencil 包含三项关键技术：

1. **Layout Transformation（布局变换）**
2. **Compute Adaptation（计算适配）**
3. **Conflicts Removal（冲突消除）**

在布局变换阶段，我们提出 **stencil2row**，构造一种适用于矩阵乘法、同时显著减少内存占用的数据布局。相比 im2row，stencil2row 可将内存占用降低 **70.0%～96.4%**。

在计算适配阶段，我们提出 **Dual Tessellation**，通过对矩阵进行镶嵌式划分，提高 Tensor Core 利用率，将其从 **12.5% 提高到 87.5%**。同时，Kernel Fusion 通过降低矩阵稀疏性，进一步提升 Tensor Core 上的计算密度。

在冲突消除阶段，我们设计 **Lookup Table**，用于避免高代价运算并减少冗余的地址计算；同时使用 **Dirty Bits Padding**，通过额外的 padding 区域写入无效数据，从而绕开条件分支，实现无冲突的计算，进一步提升性能。

与同样使用 Tensor Core 的 TCStencil 相比，ConvStencil 平均将非合并全局内存访问减少 **44.0%**，每次请求中的 bank conflict 平均减少 **63.5%**。

我们使用多种不同 stencil kernel，从三个方面展示实验结果：

1. 我们提出的各项设计与优化均有效，每项技术都带来了可测量的性能提升；
2. ConvStencil 在各种 benchmark 上均优于五种现有先进方案：cuDNN、AMOS、Brick、DRStencil 和 TCStencil；
3. ConvStencil 也优于采用三时间步融合的 DRStencil，表明性能提升并不只是来自 kernel fusion，而是也来自算法设计本身。

本文的贡献如下：

- 提出 **ConvStencil**，一种将 stencil 计算高效转换为 Tensor Core 上矩阵乘法的新型 stencil 计算系统；
- 提出 **stencil2row** 布局变换，消除 im2row 结果中的冗余，同时保持适用于矩阵乘法的高效数据布局；
- 在计算适配阶段采用 **Dual Tessellation** 提升 Tensor Core 利用率，并通过 **Kernel Fusion** 进一步提高 Tensor Core 上的计算密度；
- 在冲突消除阶段提出 **Lookup Table** 与 **Dirty Bits Padding**，消除影响性能的冲突并进一步提升性能。

---

# 2 背景与挑战

## 2.1 Stencil 计算

Stencil 计算广泛应用于科学与工程领域，其基本过程是：按照一个预先定义的计算模式，迭代地更新多维输入。

这个预定义模式称为 **shape（形状）**，主要包括两类：

- **star stencil**
- **box stencil**

Star stencil 计算中心点与其邻域点的加权和，但邻域点只能沿某一个维度偏离中心点。

Box stencil 则计算一个正方形或立方体区域内所有点的加权和，中心点位于该几何区域的中心。

具体 stencil 模式所涉及点的范围由 **radius（半径）** 决定，radius 也称作 **order（阶数）**。

例如，一个 radius = 1 的 box stencil，其计算区域就是一个 \(3\times 3\) 的正方形。

---

## 2.2 Tensor Core 上基于 GEMM 的卷积

Tensor Core 是 NVIDIA 开发的一种专用硬件组件，用于加速矩阵乘法。

其独特能力是执行混合精度矩阵乘加运算（Matrix Multiply-Accumulate, MMA），如式（1）所示：

\[
D_{m\times n}=A_{m\times k}\times B_{k\times n}+C_{m\times n}
\tag{1}
\]

这使其能够获得高于普通 CUDA Core 的计算速度。

基于 GEMM 的卷积会将卷积转换为矩阵乘法，因此成为在 Tensor Core 上执行卷积的一种高效方法。

其过程如图 1 所示。多通道输入和卷积核都会被重新整形成二维矩阵，然后将卷积操作表示为矩阵乘法。

输入矩阵通过将图像中每一个与 kernel 等大的 patch 展开为一行构造，这一过程称为 **im2row**。

kernel（或 filter）矩阵则通过把 filter 权重展开成列构造。

一个卷积操作通常包含多个卷积核，而且卷积核数通常是 2 的幂。由卷积核展开得到的多个列共同组成 kernel matrix。

随后，对这两个矩阵执行矩阵乘法。

**图 1：基于 GEMM 的卷积与 stencil。**

---

## 2.3 挑战

Convolution 与 stencil 具有高度相似的计算模式：二者都会令 kernel 在输入网格上滑动，并计算加权和。

尽管已经存在大量相关研究，但目前仍缺乏一种有效且实用的方法，使 stencil 能够高效利用 Tensor Core。

这带来一个问题：

> 为什么 stencil 无法像 convolution 一样方便地映射到 Tensor Core 上？

我们总结出三个主要挑战。

### 1. 空间爆炸

将 stencil 转换为矩阵乘法，一个直接思路是采用 im2row。

然而，im2row 会产生巨大的内存需求，转换后的矩阵可能比原始输入大数倍甚至数十倍，从而导致 **space explosion（空间爆炸）**。

例如，对于一个 \(10\times10\) 输入与 \(3\times3\) kernel，输入矩阵会被扩展为 \(100\times9\)，体积达到原始输入的 9 倍。

在普通卷积中，这种空间膨胀通常不是特别严重的问题，因为 kernel matrix 拥有足够多的列，使矩阵乘法较为稠密，因此计算开销与内存开销能够取得一定平衡。

但如图 1 所示，stencil 经 im2row 转换后得到的是矩阵—向量乘法。Tensor Core 对这种矩阵—向量乘法的利用效率很低，因此 im2row 带来的空间膨胀变得十分严重。

此外，stencil 通常要求 FP64 精度，进一步加剧了内存压力。

与此形成鲜明对比的是，GPU 上可用的共享内存非常有限。即使是 NVIDIA A100，每个 Streaming Multiprocessor（SM）也只有 **164 KB** 共享内存。

### 2. Tensor Core 利用率低

如图 1 所示，当满足以下两个条件时，卷积会退化为 stencil 计算：

1. 输入数据和卷积核的 channel 数均为 1；
2. stencil 计算中只有一个 kernel。

此时 stencil 计算实际上变成矩阵—向量乘法。

然而，在 FP64 精度下，NVIDIA A100 的 Tensor Core 只支持 \(8\times8\times4\) MMA，也就是式（1）中的：

\[
m=8,\quad n=8,\quad k=4
\]

这意味着右侧参与乘法的矩阵中，有 **7/8 的列会被浪费**。

### 3. 算法与硬件之间的冲突

即使完成了针对 Tensor Core 的算法设计，在实际映射过程中，算法实现与硬件设计之间仍会出现两类重要冲突。

第一，内存访问涉及大量重复的 offset 计算，与标准 stencil 计算过程产生冲突。这些额外计算会消耗计算资源，导致性能下降。

第二，布局变换中存在大量条件分支与 bank conflict，造成严重的 warp divergence 和串行化内存访问。

---

# 3 ConvStencil

ConvStencil 是一种利用类似 convolution 的方法在 Tensor Core 上执行 stencil 的新方案。

我们首先介绍理论性能模型，随后介绍 ConvStencil 的三个基本组成部分：

- Layout Transformation
- Compute Adaptation
- Conflict Removal

在布局变换阶段，我们提出 **stencil2row**，把输入重新组织成两个彼此不同、尺寸更小的矩阵，为之后的 Tensor Core 计算做准备。

在计算适配阶段，Dual Tessellation 会反复地从 stencil2row 矩阵中选取 tile，并在这些 tile 上应用 Tensor Core MMA，最终得到 stencil 结果。

在冲突消除阶段，我们预先计算 pointer offset，以避免代价较高的整数除法和取模运算。

此外，我们还提出 Dirty Bits Padding，利用 padding 区域消除 load bank conflict 与条件分支。

---

## 3.1 性能模型

为了从理论上展示 ConvStencil 的性能改进，我们建立如下性能模型：

\[
T=\max(T_{\mathrm{compute}},T_{\mathrm{memory}})
\tag{2}
\]

\[
T_{\mathrm{compute}}
=
\frac{1}{fN_{\mathrm{tcu}}}
\sum_{i=0}^{K_{\mathrm{tcu}}}
\left(
k_{\mathrm{tcu}_i}\times CPI_{\mathrm{tcu}_i}
\right)
\tag{3}
\]

\[
T_{\mathrm{memory}}
=
\max
\left(
\frac{data_R}{bw_G}+\frac{data_W}{bw_G},
\frac{data_{transW}}{bw_S}+\frac{data_{transR}}{bw_S}
\right)
\tag{4}
\]

其中各符号含义见表 1。

### 表 1：符号说明

| 符号 | 含义 |
|---|---|
| \(T\) | 总的核心执行时间 |
| \(T_{\mathrm{compute}}\) | 计算所需核心时间 |
| \(T_{\mathrm{memory}}\) | 内存事务所需核心时间 |
| \(f\) | GPU 频率（核心时钟） |
| \(N_{\mathrm{tcu}}\) | TCU 数量 |
| \(K_{\mathrm{tcu}}\) | TCU 指令类型数 |
| \(k_{\mathrm{tcu}_i}\) | 第 \(i\) 类 TCU 指令的数量 |
| \(CPI_{\mathrm{tcu}_i}\) | 第 \(i\) 类 TCU 指令每条所需周期数 |
| \(data_R\) | 从全局内存读取的数据量 |
| \(data_W\) | 写入全局内存的数据量 |
| \(data_{transW}\) | 写入共享内存的变换后数据量 |
| \(data_{transR}\) | 从共享内存读取的变换后数据量 |
| \(bw_G\) | 全局内存带宽 |
| \(bw_S\) | 共享内存带宽 |

> 注：GM 表示 global memory；SM 表示 shared memory。

Stencil 总执行时间由计算时间和内存访问时间共同构成。

计算时间等于时钟频率倒数与所需时钟周期数的乘积。所需周期数通过对程序中每一种指令的数量乘以该指令所需周期数，再求和得到。

在 NVIDIA A100 GPU 上，一条 FP64 MMA 指令需要 16 个周期。

内存访问时间则取不同内存层级中读写时间总和的最大值。

我们将在第 3.3 节中基于这一理论性能模型进一步分析 ConvStencil 的性能优势。

---

## 3.2 布局变换

### Stencil2row

现有 im2row 变换存在严重的内存膨胀问题。

当原始输入被转换为 im2row matrix 后，所需内存会扩大数倍。

图 2 以一个 \(7\times7\) convolution kernel 为例展示这一问题。对一个 \(m\times n\) 输入执行 im2row 后，会形成一个：

\[
(m-6)(n-6)\times49
\]

的 im2row matrix。

随着 kernel 尺寸增大，im2row 所需内存会继续增加。

Stencil2row 基于以下三个观察提出。

### 观察 1

原始输入被转换为 im2row matrix 后，其中大多数元素是重复的，因此产生空间爆炸。

如图 2 所示，im2row matrix 的第 1～6 行中的元素，实际上都是第 0 行和第 7 行中元素的重复。

### 观察 2

在 im2row 变换中，冗余行的数据排列顺序实际上已经被存储在其他非冗余行中。

例如，图 2 中 im2row matrix 的第 3 行可以分成两部分（棕色与浅蓝色）。

第一部分的数据排列可以在第 0 行找到；第二部分的数据排列可以在第 7 行找到。

这意味着，包含冗余数据的中间行——例如第 1～6 行——其结构实际上已包含于其他行——例如第 0 行和第 7 行——之中。

因此，只利用这些非冗余行，就有可能构造出中间行所对应的计算结果。

### 观察 3

共享内存位于芯片上，因此其访问延迟远低于全局内存。

表 2 给出了不同内存类型的访问延迟。

### 表 2：内存访问延迟

| 内存访问类型 | 周期数 |
|---|---:|
| Global memory | 290 |
| Shared memory（load/store） | 23 / 19 |

全局内存访问延迟比共享内存高出一个数量级以上。

基于以上三个观察，我们提出 **stencil2row**。

Stencil2row 将原始输入转换为两个更小的矩阵，在图 2 中分别标记为 **Stencil2row Matrix A** 和 **Stencil2row Matrix B**。

Stencil2row Matrix A 的第 0 行，可以理解为 im2row matrix 第 0 行的延伸。

Stencil2row Matrix A 第 0 行一直延伸至原始输入矩阵的最后一行。换言之，Stencil2row Matrix A 的末尾元素来自原始输入矩阵的最后一行。

接下来，Stencil2row Matrix A 的第 1 行可以看作 im2row matrix 第 8 行的延伸。

按相同模式继续，就可以构造出整个 Stencil2row Matrix A。

Stencil2row Matrix A 的映射函数写为：

\[
\mathbf{Y}=stencil2row_A(\mathbf{X})
=
\begin{bmatrix}
\left\lfloor \frac{y}{n_{kernel}+1}\right\rfloor\\
n_{kernel}x+y\bmod(n_{kernel}+1)
\end{bmatrix}
\tag{5}
\]

其中：

\[
\mathbf{X}=
\begin{bmatrix}
x\\
y
\end{bmatrix},
\qquad
(y+1)\bmod(n_{kernel}+1)\neq0
\]

\(\mathbf{X}\) 表示原始输入元素的索引，\(\mathbf{Y}\) 表示 Stencil2row Matrix A 元素的索引，\(n_{kernel}\) 表示 kernel 的边长。

Stencil2row Matrix B 的构造方式类似，映射函数见原论文式（6）。

Stencil2row 并不显式地在 global memory 中构造完整变换后矩阵，而是利用 global memory 与 shared memory 访问延迟的差异，在读取原始输入时于 shared memory 中即时构造 tile，再由 Tensor Core 读取这些 tile 进行矩阵乘法。

---

## 3.3 计算适配

### Dual Tessellation

A100 的 FP64 Tensor Core 支持的 MMA 形状为 \(8\times8\times4\)。直接把 stencil 当作单 kernel 的矩阵—向量乘法时，右侧 8 列只有 1 列有效，利用率只有 12.5%。

Dual Tessellation 从 stencil2row Matrix A 与 B 中分别取 tile，通过两组矩阵乘法覆盖原本分散的 stencil 计算。其目标是让一次 MMA 中更多列携带有效计算，从而把利用率提升到 87.5%。

### Kernel Fusion

对于适合融合的 stencil shape，多个相邻计算可以融合进同一矩阵运算，使 Tensor Core 中原本为 0 或无效的区域承载更多有效计算，进一步提高计算密度。

---

## 3.4 冲突消除

ConvStencil 处理两类实现层冲突：

- 重复且代价较高的 pointer offset 计算；
- shared memory bank conflict 与条件分支。

### Lookup Table

在布局变换过程中，需要计算 pointer offset，才能把数据从 global memory 转换到 shared memory。

这些计算包含大量整数除法与取模，而这些运算在 GPU 上代价很高。不同 block 中的 offset 计算还存在大量重复。

因此，论文在 host 端预先计算 pointer offset，并以 lookup table 的形式传给 CUDA kernel，从而降低布局变换中的计算开销。

### Dirty Bits Padding

Padding 改变数据映射到 shared memory bank 的方式，用于消除 load bank conflict。普通 padding 会浪费额外空间，论文进一步把无法映射进目标 stencil2row 矩阵的无用数据写入 padding 区域；这些“dirty bits”之后不会被真正使用，因此可以同时避免原本用于筛选无效数据的条件分支。

---

# 4 通用化

ConvStencil 可推广到一维和三维 stencil。

一维情况下，完成布局变换后，计算过程与二维相同。

三维 stencil 可以分解为多个二维 stencil；不同二维平面使用不同权重分别计算，最后求和。对于 star 形状的三维 stencil，不同平面尺寸不同，较小平面使用 CUDA Core，较大平面使用 Tensor Core。

---

# 5 实验评估

## 5.1 实验设置

ConvStencil 使用 **CUDA C++** 与 **WMMA API** 实现，使用 **NVCC 12.2** 编译。实验平台为 NVIDIA A100 Tensor Core GPU 与 AMD EPYC 7V13 CPU。

对比方案包括：

- cuDNN
- AMOS
- Brick
- DRStencil
- TCStencil

比较目标精度为 FP64。由于 TCStencil 只支持 FP16，论文基于 A100 上 FP16/FP64 的计算与内存差异，对 TCStencil 的结果进行估算调整后再比较。

Benchmark 包括 Heat-1D、1D5P、Heat-2D、Box-2D9P、Star-2D13P、Box-2D49P、Heat-3D、Box-3D27P。

性能指标采用 **GStencils/s**，表示每秒能够更新多少十亿个 stencil point。

## 5.2 优化拆解

实验逐步加入隐式 stencil2row、Tensor Core、padding、Dirty Bits Padding，展示各项技术带来的独立性能收益。

## 5.3 与先进方案比较

ConvStencil 在各 benchmark 上优于 cuDNN、AMOS、Brick、DRStencil 与 TCStencil。论文指出 TCStencil 的主要问题还包括大量零元素计算、较高比例的非合并全局内存访问和更严重的 bank conflict。

## 5.4 Kernel Fusion 贡献分析

与采用三时间步融合的 DRStencil-T3 比较后，论文认为 ConvStencil 的性能提升并非主要来自 kernel fusion，而是来自整体算法设计。

---

# 6 相关工作

CPU stencil 优化包括 vectorization、data reuse、tiling 等；GPU 上还广泛采用 spatial tiling、temporal tiling、unrolling、prefetching、streaming 等技术。

Brick、DRStencil 等主要利用 CUDA Core。TCStencil 是此前直接尝试把 Tensor Core 用于 stencil 的代表工作，但只支持 FP16。cuDNN 提供高度优化的 convolution API；AMOS 能将不同操作映射到包括 Tensor Core 在内的硬件，并支持与 stencil 等价的 depth-wise convolution。

---

# 7 结论

本文提出 **ConvStencil**，通过 Layout Transformation、Compute Adaptation、Conflict Removal 三部分，将 stencil 计算转换为 Tensor Core 上的矩阵乘法，并在多种 benchmark 上优于现有方案。

---

# 附录 A：Artifact Description

代码仓库：`https://github.com/microsoft/ConvStencil`

实验要求包括 NVIDIA A100 GPU、CUDA 12.2（最低可尝试 CUDA 11.0）、GCC 9.4.0、cuDNN 8.0 以上版本。

基本编译流程：

```bash
git clone https://github.com/microsoft/ConvStencil.git
mkdir -p build
cd build
cmake ..
make all -j24
```

编译后生成：

- `convstencil_1d`
- `convstencil_2d`
- `convstencil_3d`

运行格式：

```bash
convstencil_{x}d shape input_size time_interation_size options
```
