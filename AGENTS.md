# G1Move 项目说明

- 开始工作前先阅读 `HANDOFF.md`（项目目的、最终范围、当前验证状态）和 `AGENT_INTERFACE.md`（实际调用契约）。
- 完整对话保存在 `docs/conversation/CHAT_HISTORY.md`。它是历史记录，其中早期闭环定位、互锁和 HTTP 服务方案已被用户收窄，不是待实现任务。
- 当前项目是宇树 G1 原生速度接口的轻量时间换算封装。按用户最新任务推进，不自行扩展成定位、规划或全身控制系统。
- 请尽量把环境、依赖、下载和缓存放在项目文件夹内，不污染全局环境。
- 修改公共接口时同步更新 `AGENT_INTERFACE.md` 与示例。
- 区分 mock 软件验证、Ubuntu SDK 验证和真实机器人验证。`completed` 不表示实测到位，模块常驻也不等于模块自身提供平衡控制。

- 当前连接为 `yuyang@100.105.7.84`；移动项目为 `/home/yuyang/G1Move`。历史 peilab 路径已过时。
- 2026-09-22 起，物理仿真及其模型、环境、缓存、产物放在相邻的 `/home/yuyang/G1Sim`；仿真从该目录执行并先读该目录 `AGENTS.md`。本目录保留轻量移动模块、SDK环境和40项软件测试。

- SDK 环境修复（2026-09-22）：旧账号拥有 `/tmp/cdds.LOG`，会阻止新账号初始化 DDS。安装脚本用 `scripts/prepare_sdk_local.py` 从未修改的 `.deps/unitree_sdk2_python` 派生 `.deps/unitree_sdk2_python-local`，只把 SDK 日志改为本项目 `.cache/dds/cdds.<PID>.log`，实际安装派生副本。记录见 `.deps/sdk-local-validation.json`。未修改系统文件或运动接口。
