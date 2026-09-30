"""从项目根目录运行：python -m examples.basic。默认只使用模拟后端。"""

from dataclasses import asdict
import json
from pathlib import Path

from g1_move import G1Move, MotionConfig


def main() -> None:
    config_path = Path(__file__).resolve().parents[1] / "config.json"
    config = MotionConfig.from_file(config_path)
    with G1Move(backend="mock", config=config, mock_realtime=False) as robot:
        results = [
            robot.move("forward", 1.0),
            robot.move("left", 0.5),
            robot.turn("right", 90),
        ]
        results.extend(
            robot.run_sequence([
                ("move", "left", 0.5),
                ("turn", "right", 90),
                ("move", "forward", 1.0),
            ])
        )
    print(json.dumps([asdict(result) for result in results], indent=2))


if __name__ == "__main__":
    main()
