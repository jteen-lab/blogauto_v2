"""
테스트 루트 conftest.py

sys.path 설정을 한 번만 수행하여 모든 테스트에서
반복적인 경로 조작 코드를 제거합니다.
"""
import sys
import os

# app 경로 추가
app_path = os.path.abspath(os.path.dirname(__file__))
if app_path not in sys.path:
    sys.path.insert(0, app_path)

# shared 모듈 경로 추가
shared_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../shared')
)
if shared_path not in sys.path:
    sys.path.insert(0, shared_path)
