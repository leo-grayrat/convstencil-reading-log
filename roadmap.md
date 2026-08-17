Stencil 计算：模板计算，用确定的计算模板**在整个规则网格上反复滑动，并对覆盖到的数据执行同一种运算。**

一维情况

$$
\mathbf a=\left( 
\begin{array}{l}
1&2&3&4&5&6&7&8&9
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
\dots\\
7处: r_7=7a+8b+9c
$$

但是单纯算这样朴素乘加并不合适，我们有很多矩阵计算的硬件，能不能把这种计算化成**矩阵乘法**呢？

- 数据冗余
- 权重冗余
