# feat: 新增三维路面移动载荷 DLOAD

You are working in a checked-out source repository. The upstream provenance (origin remote, project name, and commit identifiers) has been removed; solve the task from the working tree and the description below alone.

## Context (de-identified)

## 改了什么

- 新增三维单层路面单轮移动载荷教学模型；
- 新增 Fortran `DLOAD` 模板，让矩形压力区按时间和积分点坐标沿 X 方向移动；
- 根据已校验 JSON 参数，为每次运行生成独立 `moving_pressure_dload.for`；
- 新增密度、接触压力、速度、轮印尺寸、横向位置和时间增量校验；
- 使用 Abaqus/Standard 动力隐式分析，并遍历全部 ODB 帧读取极值；
- 中文报告增加最大竖向位移、极值发生时间、DLOAD 文件和动力参数；
- wheel 包含 Abaqus 脚本和 Fortran 模板；
- 离线测试由 36 项增加到 44 项。

## 为什么要改

移动轮载是用户子程序的典型入门场景。这个最小示例先回答四个基础问题：Fortran 能否编译、DLOAD 能否随时间移动、动力模型能否求解、全部时间帧的结果能否稳定读取。

本 PR 暂时基于 `agent/plate-with-hole-tension`，以便复用 [redacted-ref] 中已经完成的通用模型类型、报告和测试架构。[redacted-ref] 合并后再把本 PR 的目标分支改为 `main`。

## 用户影响与安全边界

- 普通二维模型不需要 Fortran，原有运行方式保持兼容；
- 移动载荷模型需要与 Abaqus 匹配的 Visual Studio 和 Intel Fortran Classic；
- 用户不能通过 JSON 传入任意 Python 或 Fortran 脚本路径；
- 每次生成的 `.for`、CAE、ODB、对象文件和日志都位于被忽略的工作目录；
- 默认 0.7 MPa、36 km/h 和单层材料是教学参数，不是三级公路正式设计值；
- 文档明确区分路面轮胎接触荷载和桥梁规范汽车荷载。

## 验证

- 44 项离线单元测试全部通过；
- `python -m compileall -q src tests` 通过；
- Markdown 本地链接和 `git diff --check` 通过；
- wheel 构建成功，并包含 `moving_pressure_dload.for.in`；
- Abaqus 2021、Visual Studio 2019 16.4.27、Intel Fortran 19.1.[redacted-ref].311；
- DLOAD 真实编译、链接和 Abaqus/Standard 动力隐式求解成功；
- `.sta` 包含 `THE ANALYSIS HAS COMPLETED SUCCESSFULLY`；
- 211 个动力输出帧，194,964 个节点值，126,600 个应力值；
- 最大位移模 0.[redacted-sha] mm；
- 最大竖向位移绝对值 0.[redacted-sha] mm；
- 最大 Mises 应力 0.[redacted-sha] MPa。

## 后续工作

- 三层路面与层间连接；
- 双轮、双轴和真实轴载参数；
- 阻尼、边界距离和网格/时间增量收敛；
- 路面不平度与车辆—路面耦合。

## Goal

Make the change so that the project's regression tests pass. Do not edit the test files.
