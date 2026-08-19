# ConvStencil Reading Log

用于逐步阅读与理解论文 **ConvStencil: Transform Stencil Computation to Matrix Multiplication on Tensor Cores**。

## 工作方式

- 每个阅读问题单独创建一个 GitHub Issue。
- Issue 正文保留问题原文；回答、修正、补充和网页迭代都追加到评论中，不覆盖历史。
- 用户明确接受回答或产物后，Issue 以 **Completed** 关闭。
- 如果解释方向、网页或方案被明确否定并放弃，Issue 以 **Not planned** 关闭。
- 新问题如果属于已有问题的细分，在正文中互相链接，形成可追踪的问题树。

## 仓库内容

- `paper/`：原论文
- `translation/`：阅读过程中生成的中文翻译
- `demos/`：用于解释论文概念和图示的网页
- `artifacts/`：网页验证截图等中间产物
- `tools/`：为验证网页而生成的小工具/测试脚本

## 导出阅读讲义

`roadmap.md` 可通过仓库内的导出工具生成 XeLaTeX Beamer PDF：

```bash
python -m pip install -r requirements-handout.txt
python tools/export_handout.py roadmap.md
```

默认输出到 `build/handout/ConvStencil-Reading-Handout.pdf`。如果只想检查 Markdown 解析、图片准备和生成的 LaTeX，而不调用 XeLaTeX：

```bash
python tools/export_handout.py roadmap.md --tex-only
```

完整 PDF 构建需要 XeLaTeX、Beamer、`animate` 以及 TeX Live 中的 Fandol / TeX Gyre Termes 字体。Animated WebP 会拆帧后嵌入 PDF 动画，同时保留首帧作为静态后备；动画能否播放取决于 PDF 阅读器，不支持动画时仍可看到首帧。

> 本仓库是私人论文阅读记录，不作为论文或相关材料的公开再发布渠道。
