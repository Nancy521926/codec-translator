# -*- coding: utf-8 -*-
"""无控制台启动器：双击本文件运行同目录的主程序。"""
from pathlib import Path
import runpy

if __name__ == '__main__':
    runpy.run_path(str(Path(__file__).with_name('编码转译工具.py')), run_name='__main__')
