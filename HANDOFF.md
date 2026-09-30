# G1Move 项目交接：给 SSH／服务器上的接手 Agent

**2026-09-22 当前目录：** 移动模块位于 `/home/yuyang/G1Move`；全部物理仿真代码、模型、依赖、实验输出和仿真环境已分离到相邻的 `/home/yuyang/G1Sim`。仿真命令从 G1Sim 执行，使用其 `.venv`；G1Move 的 `.venv` 仅保留移动 SDK 所需依赖。G1Sim 可编辑引用本目录的 `g1_move`，不会复制一份生产实现。下文旧日期的 peilab 路径和测试数量属于历史记录，当前连接账号为 `yuyang`。本次变更不修改移动算法、默认速度或标定参数。迁移与验证记录见 [G1Sim](../G1Sim/README.md)。

更新日期：2026-09-17（Asia/Shanghai）。这是当前项目目的、最终范围和已验证状态的交接说明。完整公开聊天原文见 [CHAT_HISTORY.md](docs/conversation/CHAT_HISTORY.md)，包含最初被放弃的方案；**不要将早期方案当作当前开发要求。**

**最新仿真实施（2026-09-17）：** 已实现并完成本机 MuJoCo 实验：59项离线回归、49次主实验接口检查、30项真实SDK RPC专项检查通过。物理移动未达到请求距离/角度，公开策略的低速前倾回正现象已独立复现。所有DDS通信仅在 `lo/domain1`，未连接或操纵真实机器人。当前结果、环境补丁和复现入口见第9节及 [实验结论](../G1Sim/artifacts/simulation/full/FINDINGS.md)。

**较早的服务器接手记录（2026-09-17）：** 用户已要求并授权准备完整 SDK 环境，同时禁止任何机器人动作。本项目现位于 `peilab-System-Product-Name:/home/peilab/Chenyy/G1Move`，Ubuntu SDK 安装／导入和35项 mock 测试均已通过。所有新增环境、依赖、缓存和临时文件留在项目内；未修改系统网络、未初始化真实后端、未发送任何机器人指令。第6、7节记录当前状态；归档聊天保留此前的历史状态。

## 1. 项目为什么存在

用户团队正在做由 agent／大模型调用多个小模块操纵人形机器人的科研项目。机器人是 **Unitree G1 EDU 29DOF**。用户负责移动模块；其他成员负责上肢操作和上层规划。

移动模块需要像一个即插即用的 skill：输入“前进多少米、向左平移多少米、向右转多少度”，就按顺序执行。没有大模型时，人也能直接通过 Python 或命令行使用。这里的 skill 是机器人可调用模块，不要求实现 Codex 插件、MCP 服务或某种特定 agent 框架。

用户负责的是宇树原生控制路线：利用机器人已经具备的站立和行走控制，封装官方接口。团队另外讨论过 NVIDIA SONIC 和 Agile 路线，但本项目当前不实现它们。

目标场景是正常的室内桌面操作：移动时不进行上肢操作；上肢操作时机器人原地站立。上肢可能小幅转腰拿东西，暂不要求弯腰。移动模块本身不发送手臂、手部或腰部关节命令。

## 2. 用户最后确定的范围

用户明确要求保持简单：

> “你把宇树官方的遥控器命令翻译成skills里面运动多少米，转动多少角度不就行了，至于到底推多久摇杆换算成多少米，这个可以根据实验继续调整嘛。”

> “就是你不要做多余的事好吗。”

> “最好的情况是你甚至都不用接触真机，直接分装宇树官方的接口就行，无非是后续在真机上微调一下数值，不考虑微调数值的话，最快的话一两天就能做完。”

这些引文的原始上下文在聊天记录中保留。

当前约定：

- 做轻量的 Python 原生接口封装、命令行交互、动作组合和配置文件。
- 用速度与执行时间近似实现指定距离／角度，后续用实验调整修正系数。
- 保留基本参数检查、SDK 返回码处理、中断及零速度停止，不自动重做失败的物理动作。
- agent／调用方负责动作选择、场景判断和上下肢操作时序。
- 必须交付能让其他 agent 不读实现代码就正确调用的 Markdown 说明。
- 支持持续等待指令，但不自行实现电机支撑或实时平衡算法。
- 环境、依赖、下载、缓存尽量全部留在项目内，不污染全局 Python 或全局 PATH。

**未纳入当前范围：**里程计／定位闭环、SLAM、路径规划、避障、重心控制、全身控制、上肢互锁、HTTP 常驻服务、复杂任务调度平台、SONIC／Agile 部署。这些是早期讨论或其他路线，不要因为它们出现在历史对话中就自行添加。

## 3. 需求如何收窄：避免接手时误读

| 阶段 | 当时讨论 | 当前地位 |
| --- | --- | --- |
| 最初需求 | 常驻移动模块；空闲站立；可按距离和角度调用 | 项目目的仍然保留，站立由原生控制器承担 |
| 第一轮问答 | 有实机和 Ubuntu；希望 3 cm／2°；约一周初版；正常桌面场景、小幅转腰 | 硬件和场景背景保留，早期时间及精度要求后来被收窄 |
| 第一版助手计划 | 位置反馈闭环、互锁、HTTP 服务、5 cm／3°最低验收 | **已被用户认为过于复杂并否定** |
| 用户收窄 | 速度／时间换算、后续实验标定、1–2 天封装 | 当前实施范围 |
| 补充要求 | 增加给调用 agent 阅读的接口描述 MD | 已实现为 AGENT_INTERFACE.md |
| 用户明确要求实施 | 轻量封装＋CLI＋配置＋文档＋mock 测试 | 已完成初版 |
| 后续问答 | 只读分析风险；讨论开发者模式和自研上肢兼容性 | 没有因此增加控制功能，也没有连接真机 |
| 原交接请求 | 保存全部对话和项目目的，方便服务器上的 Codex 接手 | 本交接文件和聊天归档的来源 |
| 服务器接手请求 | 核对上传文件，在项目内准备完整 SDK 环境，不操纵机器人 | 文件校验、Ubuntu SDK 导入和 mock 验证已完成 |

3 cm／2°及5 cm／3°是历史讨论过的目标，**不是当前未上机版本已经达到的指标，也不是这版软件交付的硬验收条件**。用户仍关心实际运行表现，但接受后续上机标定；不能承诺时间换算一定达到某个精度。

## 4. 现在已有的实现

实现位于 `g1_move/`，只调用官方 `LocoClient.SetVelocity(vx, vy, omega, duration)`；不会调用 `ReleaseMode()`，不会发送全身 `rt/lowcmd`，不会切换运动 FSM，也不会主动调用 `BalanceStand` 建立站立状态。

```python
from g1_move import G1Move, MotionConfig

with G1Move(
    backend="mock",
    config=MotionConfig.from_file("config.json"),
    mock_realtime=False,
) as robot:
    robot.move("forward", 1.0)
    robot.move("left", 0.5)
    robot.turn("right", 90)
    robot.run_sequence([
        ("move", "left", 0.5),
        ("turn", "right", 90),
        ("move", "forward", 1.0),
    ])
    robot.stop()
```

请以 [AGENT_INTERFACE.md](AGENT_INTERFACE.md) 为详细接口契约，以 [README.md](README.md) 为环境及标定说明。上述示例为 mock，不连接机器人。

关键行为：

- 默认后端为 `mock`，真实后端必须显式选择 `unitree` 并指定网卡。
- 默认平移速度 `0.2 m/s`，转向速度 `15 °/s`；SDK 转向参数换算为 rad/s。
- 各方向时间修正系数初始均为 `1.0`；平移时长为距离／速度×系数，转向同理。
- 每步结束发送零速度，再等待 `pause_s=0.5` 秒。SDK 超时默认 `2.0` 秒。
- 所有动作是同步调用；一个实例同一时刻只允许一项动作或一组序列。
- 返回 `ActionResult`，包含 `kind/direction/value/unit/duration_s/status`；状态为 `completed` 或 `stopped`，失败抛异常。
- `completed` 只表示计时执行结束且零速度发送得到 SDK 成功返回，**不是实际到位或停稳的测量结果**。
- 方向按每步开始时机器人的下部朝向理解，不是地图或摄像头方向；没有航向纠偏。
- `stop()` 可从同一实例的其他线程调用；另起一个 CLI 进程发送 stop，不能取消原进程剩余序列。
- 正常退出尝试零速度清理；断网或强杀不能由软件结果推断机器人已经停稳。

此前已经修过动作启动与停止的竞争、close 失败后不能显式再停止的问题，并将 CLI 中 SDK 的普通输出导向 stderr，保持命令结果 stdout 为 JSON。回归测试需要继续保留。

## 5. 站立、自研上肢与“开发者模式”：已经讨论清楚的内容

**常驻等待的是本 Python 程序，实时产生腿部支撑力矩的是宇树原生控制器。** 当前模块只初始化为零移动、按需发速度、结束发零速度。它不检查或自动恢复原生站立模式，因此原生控制器必须已经处于兼容且可用的运动模式。

自研上肢算法并不必然要求关闭原生下肢控制。公开官方材料提供如下共存路径：

```text
自研视觉／抓取／IK／手臂轨迹 → rt/arm_sdk → 上肢
本项目 move/turn → 原生高层运动接口 → 原生下肢站立和行走
```

官方手臂示例可以发送开发者计算的关节位置、速度、增益和前馈力矩，不限于播放预设动作。相反，如果上肢程序先关闭原生运动控制，再通过 `rt/lowcmd` 接管全身关节，就不能继续指望本移动封装补上原生平衡。

截至归档时，只是查过官方公开资料，**未获得上肢程序、未确认实际机器人固件，也未完成任何共存实机验证**。当前官方并行示例说明限 Regular mode；腰部各轴和具体手部驱动的支持不能只凭29DOF型号推断。

下一步最关键的对接信息是：上肢程序最后发布 `rt/arm_sdk` 还是 `rt/lowcmd`？是否调用 `ReleaseMode()` 或以其他方式停掉原生运动服务？是否需要当前兼容模式未支持的腰部／手部控制？先弄清这个接口选择，不要因为“自研”二字就判定必须重写下肢控制。

如果上肢方案能接 Arm SDK，优先评估其发送层适配；如果确实必须全身接管，下肢平衡／行走就需要另一套控制器，这超出当前轻量封装范围。

## 6. 已验证状态与未验证事项

2026-09-16 完成软件初版；2026-09-17 原 Windows 交接验证：

```text
.venv/Scripts/python.exe -B -m unittest discover -s tests -q
Ran 35 tests in 0.893s
OK
```

验证环境为 Windows、本项目 `.venv`，Python 3.12.14。35 项测试覆盖换算、方向、配置、动作序列、预校验、SDK mock、错误／中断、停止竞争、CLI 和示例。此前也已验证可编辑安装、命令行入口、依赖检查和 Bash 脚本语法。

2026-09-17 Ubuntu 24.04.4 服务器新增验证：

- 接手前按 `HANDOFF_PACKAGE_MANIFEST.json` 核对26个文件，大小和 SHA-256 全部一致。该清单保留原交接包校验值；本次脚本和文档更新后，不再代表当前文件校验值。根目录没有 `.git`，符合原交接包排除规则。
- 系统 Python `/usr/bin/python3` 为3.12.3；默认 Conda Python 为3.13.13。系统缺少 `ensurepip`，使用已有 uv 0.11.28 创建项目 `.venv`，未安装系统软件。
- 固定版本 Unitree SDK、CycloneDDS 0.10.2、NumPy 1.26.4、OpenCV 4.10.0.84 已安装；`pip check` 通过。
- SDK 类、NumPy、OpenCV 和本项目可导入；确认动态库来自项目 `.deps/cyclonedds-install/lib/libddsc.so.0.10.2`。导入检查中 DDS Domain／Participant 未创建，进程没有 socket。
- 项目 `.venv` 中35项 mock 测试全部通过，耗时0.294秒；Python 示例、mock CLI 序列和 `g1-move` 入口通过。`completed` 仍仅为 mock 软件执行结果。
- 两份 Bash 脚本语法检查通过；安装脚本在默认 Conda 环境下复用项目 `.venv` 重复执行成功，显式指定3.13时提前拒绝。运行脚本在外部 `PYTHONHOME`／`PYTHONPATH` 无效的情况下仍能执行 mock。
- 依赖快照位于 `.deps/installed-requirements.txt`，路径与导入验证记录位于 `.deps/environment-validation.json`；首次安装、重复安装和版本拒绝日志位于 `.cache/setup-unitree.log`、`.cache/setup-unitree-rerun.log`、`.cache/setup-invalid-python.log`。

以下事项仍未验证：

- 真实 G1 的固件版本、网络连通、控制模式及持续时间参数行为。
- 实际行走／转角误差、停止距离、平衡能力和上下肢共存效果。
- 模型训练、原厂控制器的仿真等效性、SONIC／Agile部署。公开替代策略的本机物理实验已完成，见第9节。

## 7. 在 SSH／服务器上继续开发

归档使用项目内相对链接，可以随代码复制。若服务器已有改动，应先比较，不要用本包直接覆盖已有工程。Windows 的 `.venv` 不能搬到 Linux 使用，交接 ZIP 已排除环境、缓存和构建产物。

服务器用户为 `peilab`，项目根目录为 `/home/peilab/Chenyy/G1Move`，现有 `.venv` 已可使用。无需重新安装即可运行 mock：

```bash
bash scripts/run.sh --backend mock --mock-fast sequence examples/sequence.json
env -u PYTHONPATH -u PYTHONHOME PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B -m unittest discover -s tests -q
```

需要重建环境时使用 `G1MOVE_PYTHON=/usr/bin/python3 bash scripts/setup_unitree.sh`。脚本优先使用显式解释器，其次为已有项目 `.venv`、系统 `/usr/bin/python3`，最后才是 PATH 中的 Python。没有 `ensurepip` 时可使用主机已有 uv 引导 pip，所有 uv 缓存仍在项目内。缺少这些条件时明确报错，不自动使用 sudo／apt。

源码、CycloneDDS 构建及安装位于 `.deps`，Python 包位于 `.venv`，缓存和临时文件位于 `.cache`。安装与运行脚本只设置本次进程环境，清除继承的 `PYTHONPATH`／`PYTHONHOME`，不修改全局 Python、Conda、shell 或全局 PATH。系统 Python、编译工具和 uv 为复用的既有工具。

固定版本：Unitree SDK commit `65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5`；CycloneDDS 0.10.2 commit `9995905bce6c4cf9f740d6438bbf7fcfd1c83dfd`。运动 API 未改变。

本机已有 NetworkManager 配置 `loco-manip-g1`，绑定 `enp6s0`，本机静态地址 `192.168.123.222/24`，无网关。只读检查时网卡为 `NO-CARRIER`，没有活动 IP；另有旧 USB 网卡配置 `G1 enx00e04c3601b7`，该 USB 网卡当前不在设备列表中。无链路可能来自机器人关机、网线未接或其他物理连接问题，不能据此确认机器人关机。本项目通过网卡使用 DDS，未配置额外服务端口。

本次只读取本机网卡、路由和已保存连接配置，没有激活连接、修改地址或探测机器人。未构造真实后端，未发送零速度、停止或其他机器人指令。真实后端初始化本身会发零速度，不能用于禁止机器人指令时的连通性检查。

## 8. 对话与资料索引

- [完整聊天 Markdown](docs/conversation/CHAT_HISTORY.md)：原始需求、全部公开回复、三轮选项问答、早期方案和用户纠正。
- [结构化聊天 JSONL](docs/conversation/conversation.jsonl)：同一公开对话，可程序读取；正文逐条保留，含来源行号和校验值。
- [导出清单](docs/conversation/export_manifest.json)：导出截止点、消息数量、附件和 SHA-256。
- [组内思路图副本](docs/conversation/attachments/group-concept-image-1.jpg)：从会话内嵌图像恢复；原微信临时文件已不存在，不声称是原相机分辨率。
- [官方 G1 Python LocoClient，固定版本](https://github.com/unitreerobotics/unitree_sdk2_python/blob/65691c8a8bc53b98d3976dba4dbf9d5d20b2e7f5/unitree_sdk2py/g1/loco/g1_loco_client.py)。
- [官方上下肢共存说明](https://github.com/unitreerobotics/xr_teleoperate/wiki/Motion)。
- [官方自定义手臂 SDK 示例](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/g1/high_level/g1_arm7_sdk_dds_example.cpp)。
- [官方低层接管示例](https://github.com/unitreerobotics/unitree_sdk2/blob/main/example/g1/low_level/g1_dual_arm_example.cpp)。

以上官方资料是对话期间查阅的来源；最新固件兼容性需接手时按实际版本核实。历史原文中的错误、过度设计与后续修正都保留，当前项目范围以上文第2、3节及用户最新指令为准。

## 9. 本机 MuJoCo 实验交付（2026-09-17）

本次用户明确授权实现三维仿真实验及真实SDK调用链，原生产移动模块继续使用原生SetVelocity路线；仿真适配与公开行走策略仅用于虚拟机器人。

- 公共接口新增 `G1Move(..., dds_domain=0)` 和 `--dds-domain`。SDK全局初始化缓存同时检查域和网卡；仿真固定 `backend="unitree", interface="lo", dds_domain=1`，每次试次新进程。默认mock、原平移0.2 m/s、原转向15°/s未改。
- `simulation/` 提供本机sport/7105服务、公开G1-29DOF velocity/v0策略、官方G1Bridge无窗口物理入口、49次A/B实验驱动、真值分析和EGL视频。实验独立使用10°/s，周期0.002s物理/0.02s策略。
- [完整结论](../G1Sim/artifacts/simulation/full/FINDINGS.md)：49次全部完成，命令/时序/停止/错误返回及基础仿真有效性检查通过；没有达到目标距离/角度的保证。组合路径A/B终点差最大约0.365m，不能据此宣称运动重复性达标。
- [低速诊断](../G1Sim/simulation/diagnostics/README.md)：去掉封装/RPC/DDS后，同一策略在0.2m/s下仍主要前倾回正，0.3m/s下观察到迈步。没有因此修改真机配置或原主实验数据。
- 59项离线回归通过；[30项真实SDK专项检查](../G1Sim/artifacts/simulation/rpc-contract/rpc-summary.json)通过，覆盖非法参数、替换速度、TTL和显式零速度。10个主实验代表视频及0.3m/s独立诊断视频已输出，均有明确替代策略标注。
- 首次DDS实际初始化发现CycloneDDS 0.10.2配置日志中的snprintf长度错误导致Ubuntu缓冲区检查退出。`scripts/setup_unitree.sh`在`.deps/cyclonedds-patched`应用`scripts/patches/cyclonedds-0.10.2-snprintf.patch`，保留原始`.deps/cyclonedds`；安装目录仍为`.deps/cyclonedds-install`。原`.deps/environment-validation.json`是较早导入验证记录，新诊断见`.deps/cyclonedds-patch-validation.json`。
- MuJoCo3.3.7、RL Lab4960b847、Unitree MuJoCo1eb6642e、C++SDKc7538298及全部模型校验记录在`.deps/simulation-lock.json`；各次实验保存独立版本快照。依赖、缓存和编译输出均在项目内，没有sudo/apt或全局Python修改。

复现使用新输出目录：

```bash
cd /home/yuyang/G1Sim
bash scripts/setup_simulation.sh
bash scripts/run_simulation.sh --repeats 3 --output artifacts/simulation/new-run
.venv/bin/python -m simulation.render artifacts/simulation/new-run --all
```

详细操作见 [simulation/README.md](../G1Sim/simulation/README.md)。真实固件的duration/模式行为、原厂行走控制、真机精度和上下肢共存仍未验证。不要用替代策略的仿真误差反向修改真机标定。

## 给服务器 Agent 的开场提示

> 请先阅读本项目 AGENTS.md、HANDOFF.md 和 AGENT_INTERFACE.md。这个项目已有轻量的G1原生移动封装、59项离线回归和独立MuJoCo仿真实验，不是从零开发。请遵守用户最终收窄的范围，不自行添加定位、SLAM、上肢互锁或复杂服务。需要理解前因后果时读 docs/conversation/CHAT_HISTORY.md；其中早期复杂方案已被用户否定。当前已完成Ubuntu SDK与本机回环仿真验证，存在公开策略低速响应限制；未做真实机器人连接、动作或标定。读完后根据我接下来的具体任务继续，依赖和环境保持在项目内。

## 2026-09-22 目录拆分验收

仿真现位于 `/home/yuyang/G1Sim`，使用独立环境并引用当前 G1Move 源码。生产移动代码和默认配置未改变。40项移动测试、19项仿真测试、站立及前进A/B仿真、30项本机RPC检查和EGL视频渲染通过。旧账号的Python安装/构建绝对路径及SDK日志权限问题已修复。全部历史结果已核对保留；详见 [迁移验收](../G1Sim/MIGRATION_2026-09-22.md)。当前已具备进入真机首次受控验证的软件基础，未做真机动作、标定或精度验收。
