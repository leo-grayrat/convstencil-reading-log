## Stencil 计算

模板计算，用确定的计算模板**在整个规则网格上反复滑动，并对覆盖到的数据执行同一种运算。**

## 一维情况

$$
\mathbf a=\left( 
\begin{array}{l}
1&2&3&4&5&6
\end{array}
\right)
$$

有模板

$$
\mathbf w=\left( 
\begin{array}{l}
a&b&c
\end{array}
\right)
$$

计算范式即

$$
r_k=\sum_{i=k}^{k+2}a_iw_i
$$

则有

$$
1处: r_1=1a+2b+3c\\
2处: r_2=2a+3b+4c\\
3处: r_3=3a+4b+5c\\
4处: r_4=4a+5b+6c
$$

但是单纯算这样朴素乘加并不合适，我们有很多矩阵计算的硬件，能不能把这种计算化成**矩阵乘法**呢？反正都是 $\sum a_ib_i$ 乘加的形式~

为了方便讨论，鉴于这里有种对数据加权的样子，称模板向量及其元素为**权重**。

## 方法一

让我们对齐一下：
$$
\begin{align}
1处: r_1=1a+2b + \textcolor{red}{3}&c\\
2处: r_2=2a+\textcolor{red}{3}&b+\textcolor{red}{4}c\\
3处: r_3=\textcolor{red}{3}&a+\textcolor{red}{4}b+5c\\
4处: r&_4=\textcolor{red}{4}a+5b+6c\\
\end{align}
$$
可以发现，随着 stencil 在原数据上滑动，相对于原数据来看，权重也在滑动。

把权重按照滑动的方式排列成一个矩阵：
$$
\left[ 
\begin{matrix}
1&2&3&4&5&6\\
\end{matrix}
\right]
\left[ 
\begin{matrix}
a\\
b&a\\
c&b&a\\
&c&b&a\\
&&c&b\\
&&&c\\

\end{matrix}
\right]
$$
这种方法中重复排列的是

## 方法二

更简单的方法是把每个滑动窗口都抄下来。
$$
1处: r_1=1\textcolor{red}{a}+2\textcolor{red}{b}+3\textcolor{red}{c}\\
2处: r_2=2\textcolor{red}{a}+3\textcolor{red}{b}+4\textcolor{red}{c}\\
3处: r_3=3\textcolor{red}{a}+4\textcolor{red}{b}+5\textcolor{red}{c}\\
\dots\\
7处: r_7=7\textcolor{red}{a}+8\textcolor{red}{b}+9\textcolor{red}{c}
$$
显然，**权重**都是统一的。我们可以把权重**提取出来**作为一个向量：
$$
\mathbf r=\left[ 
\begin{matrix}
r_1\\
r_2\\
r_3\\
\vdots\\
r_7
\end{matrix}
\right]=
\left[ 
\begin{matrix}
1&2&3\\
2&3&4\\
3&4&5\\
&\dots\\
7&8&9
\end{matrix}
\right]
\left[ 
\begin{matrix}
\textcolor{red}{a}\\
\textcolor{red}{b}\\
\textcolor{red}{c}
\end{matrix}
\right]
=
\left[ 
\begin{matrix}
1\textcolor{red}{a}+2\textcolor{red}{b}+3\textcolor{red}{c}\\
2\textcolor{red}{a}+3\textcolor{red}{b}+4\textcolor{red}{c}\\
3\textcolor{red}{a}+4\textcolor{red}{b}+5\textcolor{red}{c}\\
\dots\\
7\textcolor{red}{a}+8\textcolor{red}{b}+9\textcolor{red}{c}
\end{matrix}
\right]
$$
