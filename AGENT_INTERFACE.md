# G1 移动接口：Agent 调用说明

**2026-09-22 当前目录：** 移动模块位于 `/home/yuyang/G1Move`；全部物理仿真代码、模型、依赖、实验输出和仿真环境已分离到相邻的 `/home/yuyang/G1Sim`。仿真命令从 G1Sim 执行，使用其 `.venv`；G1Move 的 `.venv` 仅保留移动 SDK 所需依赖。G1Sim 可编辑引用本目录的 `g1_move`，不会复制一份生产实现。下文旧日期的 peilab 路径和测试数量属于历史记录，当前连接账号为 `yuyang`。本次变更不修改移动算法、默认速度或标定参数。迁移与验证记录见 [G1Sim](../G1Sim/README.md)。

此接口控制 Unitree G1 EDU 29DOF 的原生移动能力。Agent 负责动作选择和场景判断，本模块负责将明确的移动、转向命令换算为速度与执行时间，并在结束时发送零速度。

## 能力与调用前提

- 支持前进、后退、左右侧移、左右转向，以及这些动作的顺序组合。
- 使用时间换算，无定位反馈；`completed` 不代表已测量确认到位。初始参数未标定，实际精度未知。
- 真机必须已经按官方流程处于兼容的原生运动控制模式，调用主机已接通机器人网络。
- 调用方负责安排移动与上肢操作的时序，避免多个程序同时发布移动命令。
- 本模块不控制手臂、腰部和关节力矩，不实现避障、路径规划或平衡算法。无移动任务时沿用机载原生站立控制。
- 进程正常退出会尝试发送零速度；断网、强制结束进程时无法确认停止成功，不应将其报告为机器人已停稳。

所有下列命令和示例均从项目根目录执行。默认使用 `mock` 软件后端；`unitree` 表示使用官方 SDK，其目标可以是真机，也可以是显式配置的本机仿真服务。

## 项目环境准备（不连接机器人）

Ubuntu 使用项目 `.venv`；完整 SDK 环境通过以下命令安装，解释器须为 Python 3.10–3.12：

```bash
G1MOVE_PYTHON=/usr/bin/python3 bash scripts/setup_unitree.sh
bash scripts/run.sh --backend mock --mock-fast sequence examples/sequence.json
```

`G1MOVE_PYTHON` 只影响安装解释器选择。省略时优先复用项目 `.venv`，其次使用系统 Python；运行脚本固定使用项目 `.venv/bin/python`。下载、构建及缓存保存在 `.deps`、`.cache`，不需要修改全局 Python 或 shell 配置。系统缺少 `ensurepip` 时，安装脚本可借助已有 `uv` 创建项目环境；详见 README。

安装后的检查只导入 SDK 类，不初始化 DDS。`unitree` 后端构造会向所选 DDS 域和网卡发送零速度；禁止机器人指令时，不得使用机器人网卡启动该后端。当前授权的仿真实验固定使用 `interface="lo"`、`dds_domain=1`，仅连接本机仿真服务。

## 导入、初始化与关闭

```python
from dataclasses import asdict
from g1_move import G1Move, MotionConfig, MotionError, BusyError

config = MotionConfig.from_file("config.json")
with G1Move(
    backend="mock",
    interface=None,
    config=config,
    mock_realtime=False,
) as robot:
    result = robot.move("forward", 1.0)
    print(asdict(result))
```

构造参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| `backend` | `"mock"` | `"mock"` 为软件记录后端；`"unitree"` 为官方 SDK |
| `interface` | `None` | `unitree` 必须显式指定网卡；真机如 `"eth0"`，本机仿真为 `"lo"` |
| `dds_domain` | `0` | DDS 域编号，非负整数且不接受布尔值；本机仿真实验固定为 `1` |
| `config` | `MotionConfig()` | 执行速度、修正系数、停顿和 SDK 超时配置 |
| `mock_realtime` | `True` | 模拟后端是否等待计划时长；`False` 只验证调用逻辑 |

真实调用替换为：

```python
with G1Move(backend="unitree", interface="eth0", config=config) as robot:
    robot.move("forward", 0.2)
```

初始化会发送一次零速度，不切换运动模式。复用同一实例执行连续动作。`with` 退出时发送零速度并关闭该实例，不关闭机器人的原生控制程序。`unitree` 后端不允许设置 `mock_realtime=False`。

DDS 在同一进程内共享初始化。第一次通过本模块初始化后，后续实例必须使用相同的 `(dds_domain, interface)`，否则抛出 `MotionError`；关闭实例不会重置 DDS。官方 SDK 的全局单例也可能已被其他代码初始化，本模块不能识别或覆盖外部初始化的配置，因此每个仿真试次及 A/B 组使用全新进程，并由 G1Move 首次初始化 DDS。

本机 MuJoCo 仿真调用示例（先按 [仿真说明](../G1Sim/simulation/README.md) 启动本机服务）：

```python
with G1Move(
    backend="unitree", interface="lo", dds_domain=1,
    config=MotionConfig(angular_speed_deg_s=10.0),
) as robot:
    robot.move("forward", 0.4)
    robot.turn("left", 30.0)
```

完整脚本见 [examples/simulation.py](../G1Sim/examples/simulation.py)。仿真策略使用 10°/s 转向；本模块默认 15°/s 不变。仿真服务提供替代行走控制器，验证通过不等于原厂固件或真机通过。

## 方法和参数

| 方法 | 参数 | 返回值 |
| --- | --- | --- |
| `move(direction, distance_m)` | `direction` 为 `forward`、`backward`、`left` 或 `right`；距离单位为米 | `ActionResult` |
| `turn(direction, angle_deg)` | `direction` 为 `left` 或 `right`；角度单位为度 | `ActionResult` |
| `run_sequence(actions)` | 由三元组 `(kind, direction, value)` 组成的非空列表或元组，`kind` 为 `move` 或 `turn` | 已处理步骤的 `list[ActionResult]` |
| `stop()` | 无参数；中止当前实例的执行并发送零速度 | `None`，不返回位置反馈 |
| `close()` | 发送零速度并关闭实例；`with` 自动调用 | `None` |

距离和角度必须是正的有限实数，不接受 `0`、负值、布尔值、NaN 或无穷大。用方向表示正反向，不传负距离。需要不移动时不调用动作，或调用 `stop()`。

方向约定：

| 命令 | 含义 | SDK 速度符号 |
| --- | --- | --- |
| `move("forward", d)` | 向前平移 | `vx > 0` |
| `move("backward", d)` | 向后平移 | `vx < 0` |
| `move("left", d)` | 向左侧移，保持零转向指令 | `vy > 0` |
| `move("right", d)` | 向右侧移，保持零转向指令 | `vy < 0` |
| `turn("left", a)` | 向左转 | `omega > 0` |
| `turn("right", a)` | 向右转 | `omega < 0` |

方向相对于**每一步开始时机器人下部的朝向**，不是地图方向、摄像头方向或腰部旋转后的上身朝向。这是命令语义，没有航向反馈纠偏。

## 执行语义与返回值

动作是同步阻塞调用。同一实例同时只允许一个移动动作或一个动作组合；第二个并发动作抛出 `BusyError`。`stop()` 可以在另一个线程中调用，以中止正在执行的动作。

每个动作发送非零速度，等待换算后的时长，再发送零速度并等待 `pause_s`，然后返回。单步调用和序列最后一步也包含这段停顿。序列在任何移动开始前检查所有动作参数，避免执行到一半才发现后续参数错误。遇停止后终止剩余步骤，遇执行失败后抛异常并终止，不自动重试。

返回的 `ActionResult` 是 dataclass，用 `dataclasses.asdict(result)` 获得可序列化字典：

```json
{
  "kind": "move",
  "direction": "forward",
  "value": 1.0,
  "unit": "m",
  "duration_s": 5.0,
  "status": "completed"
}
```

- `kind`：`move` 或 `turn`。
- `direction`：请求的方向。
- `value`：请求的距离或角度。
- `unit`：`m` 或 `deg`。
- `duration_s`：计划非零速度指令时长，不含结束后的 `pause_s`，不是实测运动时间或中断前已用时间。
- `status`：`completed` 表示计划执行已结束；`stopped` 表示被停止请求中断。

序列返回已处理步骤的结果列表，不包含后续未处理的步骤。最后一个 `stopped` 步骤可能在发出非零命令之前就被取消，不能从结果推断实际移动量。停止成功表示 SDK 接受了零速度命令，不代表已测量确认停稳。

## 异常与中断

| 情况 | 表现 | 调用方处理 |
| --- | --- | --- |
| 方向、数值或配置非法 | `ValueError` | 修正输入后再调用 |
| 同一实例已有动作执行中 | `BusyError`，继承 `MotionError` | 等待现有动作，或主动停止后再安排动作 |
| SDK 返回非零码或执行错误 | `MotionError` | 当前动作或序列失败；查看错误，确认状态后决定下一次调用 |
| 读取配置文件失败 | `OSError`；JSON 格式错误属于 `ValueError` | 检查文件路径、权限和格式 |
| Python 中按 `Ctrl+C` | 尝试零速度清理后抛 `KeyboardInterrupt` | 不继续当前序列，可捕获后结束程序 |

失败的物理动作不自动重试，因为其可能已经部分执行。异常时不能假设机器人没有移动，也不能把失败当成到达目标。

`close()` 发送零速度失败时会抛出异常，实例不再接受新移动；调用方仍可显式再次调用 `close()` 或 `stop()` 尝试停止。关闭成功后，重复 `close()` 不再发送命令。

中断与错误处理示例：

```python
from g1_move import G1Move, MotionError

try:
    with G1Move(backend="mock") as robot:
        robot.run_sequence([
            ("move", "forward", 1.0),
            ("turn", "right", 90),
        ])
except KeyboardInterrupt:
    print("执行已中断；零速度清理已尝试。")
except (ValueError, MotionError) as exc:
    print(f"调用失败：{exc}")
```

## 完整动作组合

```python
from dataclasses import asdict
from g1_move import G1Move, MotionConfig

with G1Move(
    backend="mock",
    config=MotionConfig.from_file("config.json"),
    mock_realtime=False,
) as robot:
    robot.move("forward", 1.0)
    robot.turn("left", 90)
    results = robot.run_sequence([
        ("move", "left", 0.5),
        ("turn", "right", 90),
        ("move", "forward", 1.0),
    ])
    print([asdict(result) for result in results])
```

## 命令行调用

全局选项放在子命令之前：

```bash
python -m g1_move --backend mock --mock-fast move forward 1
python -m g1_move --backend mock --mock-fast turn right 90
python -m g1_move --backend mock --mock-fast sequence examples/sequence.json
python -m g1_move --backend mock shell
```

实机示例：

```bash
bash scripts/run.sh --backend unitree --interface eth0 --config config.json shell
```

本机仿真 CLI 必须显式使用 `--interface lo --dds-domain 1`。例如服务已启动后可运行：

```bash
cd /home/yuyang/G1Sim
bash scripts/run.sh --config simulation/motion_config.json move forward 0.4
```

`--dds-domain` 默认 `0`；它是全局选项，放在子命令之前。仿真转向还须显式加载转向速度为 10°/s 的实验配置，不能使用 `--mock-fast`。

`sequence` 文件为 JSON 数组：

```json
[
  ["move", "left", 0.5],
  ["turn", "right", 90],
  ["move", "forward", 1.0]
]
```

`move`、`turn` 输出单个结果 JSON，`sequence` 输出结果数组，`stop` 输出 `{"status": "stop_requested"}`。错误以 `{"error": "说明", "error_type": "异常类型"}` 输出到 stderr，正常结果输出到 stdout。

交互模式支持相同的动作命令和 `stop`、`help`、`exit`（或 `quit`），不传子命令也会进入交互模式。执行中使用 `Ctrl+C` 中断并返回提示符；空闲时按 `Ctrl+C` 则退出交互。

独立 CLI `stop` 只发送一次零速度，不负责取消其他进程的任务。一个运行进程应作为唯一移动命令来源；需要中止它时使用该进程中的中断或同一实例的 `stop()`。

独立 CLI 退出码为：成功 `0`、执行错误 `1`、参数错误 `2`、`Ctrl+C` 中断 `130`。

## 默认参数与能力边界

默认平移速度为 `0.2 m/s`、转向速度为 `15 °/s`；各方向时间修正系数为 `1.0`，每个动作结束后停顿为 `0.5 s`，SDK 超时为 `2.0 s`。命令行省略 `--config` 时使用内置默认值，不自动读取 `config.json`；使用标定文件时显式传入 `--config config.json`。Python 使用 `MotionConfig.from_file("config.json")` 后将其传入构造函数。

```text
move 的 duration_s = distance_m / linear_speed_mps × move_time_factors[direction]
turn 的 duration_s = angle_deg / angular_speed_deg_s × turn_time_factors[direction]
```

没有定位反馈、自动误差纠正或实测到达判据。`mock_realtime=False` / `--mock-fast` 不执行物理仿真，不可据此推断真实轨迹、平衡、制动距离或精度。实机换算系数由后续实验调整，方法见 [README.md](README.md)。
