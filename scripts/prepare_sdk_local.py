"""Keep upstream SDK pristine; derive a project-local copy with local DDS logs."""
import hashlib
import json
from pathlib import Path
import shutil
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    source = root / '.deps/unitree_sdk2_python'
    destination = root / '.deps/unitree_sdk2_python-local'
    assert source.is_dir() and source.resolve().is_relative_to(root)
    assert destination.resolve().is_relative_to(root)
    log_dir = root / '.cache/dds'
    log_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '*.egg-info', 'build', 'dist'))
    rel = Path('unitree_sdk2py/core/channel_config.py')
    original = (source / rel).read_text()
    assert original.count('/tmp/cdds.LOG') == 1, 'Upstream logging configuration changed; review before patching.'
    target = str(log_dir / 'cdds.${CYCLONEDDS_PID}.log')
    (destination / rel).write_text(original.replace('/tmp/cdds.LOG', target))
    evidence = {'source': str(source), 'installed_copy': str(destination),
                'change': 'DDS trace output path only; original SDK checkout unchanged',
                'original_sha256': hashlib.sha256((source / rel).read_bytes()).hexdigest(),
                'derived_sha256': hashlib.sha256((destination / rel).read_bytes()).hexdigest(),
                'output_template': target}
    (root / '.deps/sdk-local-validation.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Prepared SDK with project-local DDS logs:', destination)


if __name__ == '__main__':
    main()
