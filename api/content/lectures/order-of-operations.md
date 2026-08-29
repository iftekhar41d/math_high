# Order of Operations

When an expression mixes operations, everyone must evaluate it the same way or
we would get different answers. The agreed order is often remembered as
**BIDMAS**:

1. **B**rackets
2. **I**ndices (powers and roots)
3. **D**ivision and **M**ultiplication, left to right
4. **A**ddition and **S**ubtraction, left to right

Division and multiplication share a level — you work them left to right as they
appear. The same is true of addition and subtraction.

::: example Working through the levels
$$6 + 2 \times (5 - 1)^2 \div 4.$$

- Brackets: $5 - 1 = 4$, giving $6 + 2 \times 4^2 \div 4$.
- Indices: $4^2 = 16$, giving $6 + 2 \times 16 \div 4$.
- Multiply/divide left to right: $2 \times 16 = 32$, then $32 \div 4 = 8$.
- Add: $6 + 8 = 14$.
:::

::: callout A common trap
In $20 - 8 + 3$, work left to right: $20 - 8 = 12$, then $12 + 3 = 15$. Doing the
addition first ($8 + 3 = 11$, then $20 - 11 = 9$) is **wrong**.
:::

## Negatives and brackets

A negative sign in front of a bracket multiplies everything inside by $-1$:
$$10 - (4 - 7) = 10 - (-3) = 13.$$
Evaluate the bracket first, then deal with the subtraction.
