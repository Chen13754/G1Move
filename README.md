# G1 原生移动 Skill

**2026-09-22 当前目录：** 移动模块位于 `/home/yuyang/G1Move`；全部物理仿真代码、模型、依赖、实验输出和仿真环境已分离到相邻的 `/home/yuyang/G1Sim`。仿真命令从 G1Sim 执行，使用其 `.venv`；G1Move 的 `.venv` 仅保留移动 SDK 所需依赖。G1Sim 可编辑引用本目录的 `g1_move`，不会复制一份生产实现。下文旧日期的 peilab 路径和测试数量属于历史记录，当前连接账号为 `yuyang`。本次变更不修改移动算法、默认速度或标定参数。迁移与验证记录见 [G1Sim](../G1Sim/README.md)。

面向 Unitree G1 EDU 29DOF 的轻量 Python 封装：把“移动多少米”和“转动多少度”换算成官方速度命令及持续时间，供人工或 agent 调用。

没有移动指令时，机器人继续由已经启动的原生控制器维持站立；本模块不实现平衡算法，不发送手臂、腰部关节命令，也不做定位和路径规划。调用方负责安排移动与上肢操作。

**采用时间换算；2026-09-30 已保存 2026-09-25 实机实验选定的方向时间系数。** 动作完成只表示计划执行时间结束、零速度命令已被 SDK 接受，不表示测量确认到位。`mock` 验证调用逻辑，不模拟机器人的物理运动。

## 快速开始：无需机器人

以下命令均从项目根目录运行，需要 Python 3.10 或更新版本。模拟后端只依赖 Python 标准库，无需安装宇树 SDK。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m g1_move --mock-fast move forward 1
.\.venv\Scripts\python.exe -m g1_move --mock-fast sequence examples/sequence.json
.\.venv\Scripts\python.exe -m examples.basic
```

Ubuntu：

```bash
python3 -m venv .venv
.venv/bin/python -m g1_move --mock-fast move forward 1
.venv/bin/python -m g1_move --mock-fast sequence examples/sequence.json
.venv/bin/python -m examples.basic
```

默认后端为 `mock`。默认按实际命令时长等待，`--mock-fast` 跳过等待，仅适用于模拟后端。命令行省略 `--config` 时使用代码内置默认值；要使用标定后的文件，显式传入 `--config config.json`。

## MuJoCo 三维实验：无需机器人

完整实验使用真实SDK连接本机仿真服务，并由公开G1 29DOF策略驱动MuJoCo。它与mock分别验证：mock检查软件逻辑，三维实验检查本机SDK调用链及替代策略响应，真机精度仍需另行验证。

```bash
cd /home/yuyang/G1Sim
bash scripts/setup_simulation.sh
bash scripts/run_simulation.sh --repeats 3 --output artifacts/simulation/new-run
MUJOCO_GL=egl .venv/bin/python -m simulation.render artifacts/simulation/new-run --all
```

每次运行选择新的输出目录。实验固定 `lo` 和 DDS 域 `1`，不连接机器人；使用独立10°/s转向配置，不修改原默认15°/s。详细实验、输出及限制见 [simulation/README.md](../G1Sim/simulation/README.md)。

## Python 调用

```python
from dataclasses import asdict
from g1_move import G1Move, MotionConfig

config = MotionConfig.from_file("config.json")
with G1Move(backend="mock", config=config, mock_realtime=False) as robot:
    result = robot.move("forward", 1.0)
    print(asdict(result))
    robot.move("left", 0.5)
    robot.turn("right", 90)
    results = robot.run_sequence([
        ("move", "left", 0.5),
        ("turn", "right", 90),
        ("move", "forward", 1.0),
    ])
```

方法默认阻塞至当前动作结束。每一步相对于该步开始时机器人的下部朝向；左移是侧向平移，左转是原地转向。每个动作发送零速度后等待 `pause_s` 再返回，单步调用和序列最后一步也包含这段停顿。

上下文退出时发送零速度。Python 中 `Ctrl+C` 会先尝试发送零速度，再传播 `KeyboardInterrupt`。如需在动作执行中从程序主动调用 `stop()`，应从另一个线程调用；同步执行的同一个线程需要等动作返回后才能运行下一行。

面向 agent 的完整参数、返回值、异常与示例见 [AGENT_INTERFACE.md](AGENT_INTERFACE.md)。

## 命令行与常驻交互

```bash
python -m g1_move --mock-fast move left 0.5
python -m g1_move --mock-fast turn right 90
python -m g1_move --mock-fast sequence examples/sequence.json
python -m g1_move shell
```

无子命令时也进入交互模式。交互中输入：

```text
move forward 1
turn right 90
sequence examples/sequence.json
stop
exit
```

交互进程持续等待输入，动作同步执行。执行中按 `Ctrl+C` 中止当前动作并返回提示符；不会继续执行本组剩余动作。命令结果以 JSON 输出。

独立命令 `python -m g1_move stop` 使用所选后端发送零速度。它不连接或取消另一个正在运行的 Python 进程中的任务；不要用两个进程同时控制机器人。需要中止当前交互动作时使用 `Ctrl+C`，在 Python 中使用同一 `robot` 实例的 `stop()`。

脚本退出码：成功为 `0`，执行错误为 `1`，参数错误为 `2`，`Ctrl+C` 中断为 `130`。

## Ubuntu 实机环境

使用 Python 3.10–3.12。环境准备无需机器人开机或联网；主机只需能下载公开依赖，并已有 Git、CMake、make、C/C++ 编译器和 Python 开发头文件。脚本不调用 `sudo` 或 `apt`。

```bash
G1MOVE_PYTHON=/usr/bin/python3 bash scripts/setup_unitree.sh
bash scripts/run.sh --backend mock --mock-fast sequence examples/sequence.json
```

`G1MOVE_PYTHON` 可指定解释器；省略时依次选择已有项目 `.venv/bin/python`、`/usr/bin/python3`、PATH 中的 `python3`。脚本先验证 Python 版本并准备带 pip 的 `.venv`，再下载和编译 SDK。Python 提供 `venv` 和 `ensurepip` 时使用标准虚拟环境；缺少它们时使用主机已有的 `uv` 引导 pip，禁止自动下载 Python。两条路径都不可用时明确退出，不自动安装系统软件。

下载、构建、安装、缓存和临时文件均保存在本项目目录。安装与运行脚本清除继承的 `PYTHONPATH`、`PYTHONHOME`，禁用用户 Python 包目录；安装还禁用 pip 配置文件以及外部安装目标。环境变量只对脚本进程生效，不修改全局 Python、Conda、shell 配置或全局 PATH。

安装结束仅导入 SDK 类和本项目，不创建机器人客户端、不初始化 DDS、不发送机器人命令。后续经操作员确认可进行实机操作时，才使用真实后端，并将 `eth0` 替换为实际连接机器人的网卡名称：

```bash
bash scripts/run.sh --backend unitree --interface eth0 --config config.json shell
```

注意：真实后端初始化本身会发送零速度，不能用上述命令进行“只检查连接”的测试。网络受限或系统构建工具缺失时按错误信息处理，不改为全局 `pip install`。

| 项目 | 固定版本或位置 |
| --- | --- |
| `unitree_sdk2_python` | commit `65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5`，下载至 `.deps/unitree_sdk2_python` |
| CycloneDDS | 0.10.2，commit `9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd` |
| CycloneDDS 安装目录 | `.deps/cyclonedds-install`；保留0.10.2版本，附本项目snprintf修复 |
| Python 虚拟环境 | `.venv` |
| pip、uv、通用缓存及临时文件 | `.cache/pip`、`.cache/uv`、`.cache`、`.cache/tmp` |

本机首次实际初始化DDS时发现CycloneDDS 0.10.2的配置日志格式化长度错误会触发Ubuntu的缓冲区检查。安装脚本在派生源码 `.deps/cyclonedds-patched` 应用 [两处长度修复](scripts/patches/cyclonedds-0.10.2-snprintf.patch)，保留原始checkout与编译器检查；不改全局库。诊断与验证记录位于 `.deps/cyclonedds-patch-validation.json`。

`scripts/run.sh` 自动切换到项目根目录，并设置项目 CycloneDDS 动态库路径和缓存目录。SDK 安装与导入验证、mock 软件验证、真实机器人验证分别记录；环境安装成功不代表实机可用。

复制到 Ubuntu 时不要复制 Windows 的 `.venv`、`.cache` 或 `__pycache__`；在 Ubuntu 项目目录重新运行安装脚本。直接依赖版本固定在 `requirements-unitree.txt`，安装后的完整依赖快照保存在 `.deps/installed-requirements.txt`。

运行前由操作员按官方流程启动兼容的原生运动控制模式。本模块不自动起身、不切换运动模式、不关闭原生控制器。首次接入需确认当前固件接受速度命令及其持续时间，并能正确响应零速度命令。

Python 实机调用使用同一 API：

```python
from g1_move import G1Move, MotionConfig

with G1Move(
    backend="unitree",
    interface="eth0",
    config=MotionConfig.from_file("config.json"),
) as robot:
    robot.move("forward", 0.2)
```

封装的官方接口为 [`LocoClient.SetVelocity(vx, vy, omega, duration)`](https://github.com/unitreerobotics/unitree_sdk2_python/blob/master/unitree_sdk2py/g1/loco/g1_loco_client.py)。`vx`、`vy` 单位为 m/s，`omega` 为 rad/s，`duration` 为秒。每个非零命令都带计划执行时长，动作结束发送 `SetVelocity(0, 0, 0, 1.0)`；非零 SDK 返回码作为失败处理，不自动重试物理动作。

## 配置与后续标定

[config.json](config.json) 与 `MotionConfig()` 内置默认值一致，采用 [实机校准记录](docs/CALIBRATION.md) 中的最终实验系数：

| 配置 | 默认值 | 含义 |
| --- | --- | --- |
| `linear_speed_mps` | `0.2` | 平移指令速度，m/s |
| `angular_speed_deg_s` | `15.0` | 转向指令角速度，°/s |
| `move_time_factors` | 前 `1.204819`、后 `1.369318`、左 `1.838235`、右 `1.225467` | 前、后、左、右的时间修正系数 |
| `turn_time_factors` | 左、右均为 `1.62` | 转向时间修正系数 |
| `pause_s` | `0.5` | 每个动作结束后的停顿秒数，包含单步和序列最后一步 |
| `rpc_timeout_s` | `2.0` | SDK 调用超时秒数 |

执行时间：

```text
平移：T = distance_m / linear_speed_mps × 对应方向的时间修正系数
转向：T = angle_deg / angular_speed_deg_s × 对应方向的时间修正系数
```

速度与修正系数必须为正有限数，停顿时间必须为非负有限数。当前系数来自各方向最终一次实测；前进 3 米复测实际为 2.76 米，因此不保证任意距离、角度或工况的精度。

后续在相同速度、地面和正常工况下，重复测量某一方向的请求量与实际运动量，按以下公式微调该方向系数：

```text
新系数 = 旧系数 × 请求距离或角度 / 实测距离或角度
```

实测量必须大于零。前后左右和左右转分别标定；可用多次实验的平均值减少测量波动。调整后重新验证单步和组合动作。该换算是开环近似，起停过程、负载和地面变化均可能使误差不同，不能把一次标定当作所有距离的精度保证。

## 验证

```bash
python -m unittest discover -s tests -v
python -m examples.basic
python -m g1_move --mock-fast sequence examples/sequence.json
```

自动测试验证方向符号、单位与时间换算、动作顺序、参数检查、停止和 SDK 错误处理。无需真机即可完成软件验收；真实运动精度、固件持续时间行为和正常场景站立表现仍需首次上机确认。

2026-09-16 Windows 验证：Python 3.12.14，35 项自动测试全部通过；Python 示例、命令行组合、项目内可编辑安装、`g1-move` 入口与依赖检查通过，两份 Bash 脚本语法检查通过。

2026-09-17 Ubuntu 服务器验证：Ubuntu 24.04.4、项目 Python 3.12.3，固定版本 SDK 与 CycloneDDS 已在项目内安装；`pip check`、SDK／NumPy／OpenCV 导入、35 项 mock 测试（0.294 s）、Python 示例和 CLI 入口均通过。确认加载 `.deps/cyclonedds-install/lib/libddsc.so.0.10.2`，导入检查没有创建 DDS Domain／Participant，也没有打开 socket。默认 Conda 环境下重复安装成功，显式指定 Python 3.13 时在下载前拒绝。

服务器已有 `loco-manip-g1` 网络配置，绑定 `enp6s0`，本机静态地址为 `192.168.123.222/24`。检查时网卡无链路、无活动 IP；这是本机地址，不是已确认的机器人 IP。没有激活或修改网络配置，没有初始化真实机器人后端，也没有发送任何机器人指令；机器人电源状态及实机可用性仍未验证。详细记录见 [HANDOFF.md](HANDOFF.md)，本机依赖和路径记录见 `.deps/environment-validation.json`。

### 2026-09-17 本机三维实验结果

59项离线回归、49次主实验接口检查和30项真实SDK专项检查通过。公开替代策略的低速位移与转角响应明显不足，不能据此确认请求距离或角度已完成；主实验和真机默认参数均未因诊断而改变。详见 [实验结论与视频](../G1Sim/artifacts/simulation/full/FINDINGS.md)。所有DDS通信仅使用lo/domain1，未连接真实机器人。

- SDK 环境修复（2026-09-22）：旧账号拥有 `/tmp/cdds.LOG`，会阻止新账号初始化 DDS。安装脚本用 `scripts/prepare_sdk_local.py` 从未修改的 `.deps/unitree_sdk2_python` 派生 `.deps/unitree_sdk2_python-local`，只把 SDK 日志改为本项目 `.cache/dds/cdds.<PID>.log`，实际安装派生副本。记录见 `.deps/sdk-local-validation.json`。未修改系统文件或运动接口。
