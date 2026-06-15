"""Runtime hook for onnxruntime - force CPU mode only"""

import os
import sys

# 强制禁用所有非 CPU 提供程序
os.environ['ONNXRUNTIME_DISABLE_PROVIDERS'] = 'AzureExecutionProvider,TensorRTExecutionProvider,CUDAExecutionProvider,DmlExecutionProvider,OpenVINOExecutionProvider'

# 设置 onnxruntime 日志级别为 ERROR
os.environ['ONNXRUNTIME_LOG_SEVERITY_LEVEL'] = '3'

# 如果是打包环境，设置额外的环境变量
if getattr(sys, 'frozen', False):
    # 禁用 AzureExecutionProvider 的自动发现
    os.environ['ORT_DISABLE_AZURE'] = '1'
    # 强制使用 CPU
    os.environ['ONNXRUNTIME_FORCE_CPU'] = '1'

# ===== 预导入 urllib3 resolver 模块 =====
# 修复 PyInstaller 打包后动态 importlib 相对导入找不到模块的问题
# urllib3.contrib.resolver.factories 会动态 importlib.import_module(".system", ...)
# 预导入后 sys.modules 有缓存，动态导入直接命中
try:
    import urllib3.contrib.resolver
    import urllib3.contrib.resolver.system
    import urllib3.contrib.resolver.doh
    import urllib3.contrib.resolver.doq
    import urllib3.contrib.resolver.dot
    import urllib3.contrib.resolver.dou
    import urllib3.contrib.resolver.protocols
    import urllib3.contrib.resolver.factories
    import urllib3.contrib.resolver._async
    import urllib3.contrib.resolver._async.system
    import urllib3.contrib.resolver._async.doh
    import urllib3.contrib.resolver._async.doq
    import urllib3.contrib.resolver._async.dot
    import urllib3.contrib.resolver._async.dou
except Exception:
    pass
