# ConvStencil Reading Log

用于逐步阅读与理解论文 **ConvStencil: Transform Stencil Computation to Matrix Multiplication on Tensor Cores**。

- Issues 内有 **AI 问答全记录**，附有详实标签。
  - 其中标签为 `good first issue` 表示很重要， `enhancement` 和讨论中AI含糊其辞被我抓住分析、最终引出实验的内容有关。
- 仓库内主要是**浓缩了个人阅读和思考精华的[自写讲义](roadmap.md)**。
  - 还有其他理解过程中 AI 生成的图片网页（多为废案），以及翻译稿（很奇怪很不正式）。
- `experiments` 文件夹内是在 [#59](https://github.com/leo-grayrat/convstencil-reading-log/issues/59) 的启发下进行的临时实验。
  - 用于验证**个人思考得出的零冗余**是否为一条可行有效道路。

> ## 工作方式
>
> - 每个阅读问题单独创建一个 GitHub Issue。
> - Issue 正文保留问题原文；回答、修正、补充和网页迭代都追加到评论中，不覆盖历史。
> - 用户明确接受回答或产物后，Issue 以 **Completed** 关闭。
> - 如果解释方向、网页或方案被明确否定并放弃，Issue 以 **Not planned** 关闭。
> - 新问题如果属于已有问题的细分，在正文中互相链接，形成可追踪的问题树。
>
> ## 仓库内容
>
> - `paper/`：原论文
> - `translation/`：阅读过程中生成的中文翻译
> - `demos/`：用于解释论文概念和图示的网页
> - `artifacts/`：网页验证截图等中间产物
> - `tools/`：为验证网页而生成的小工具/测试脚本
>
